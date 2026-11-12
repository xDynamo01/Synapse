//! Local Windows transport for the existing v1 protocol.
use crate::runner::{owner_sid, sid_text};
use std::{
    fs::{File, OpenOptions},
    io,
    mem::size_of,
    os::windows::fs::OpenOptionsExt,
    os::windows::io::{AsRawHandle, FromRawHandle},
    ptr::null_mut,
};
use windows_sys::Win32::{
    Foundation::{ERROR_NO_DATA, ERROR_PIPE_CONNECTED, INVALID_HANDLE_VALUE, LocalFree},
    Security::{
        Authorization::{
            ConvertStringSecurityDescriptorToSecurityDescriptorW, GetSecurityInfo, SE_FILE_OBJECT,
        },
        OWNER_SECURITY_INFORMATION, SECURITY_ATTRIBUTES,
    },
    Storage::FileSystem::{
        FILE_FLAG_FIRST_PIPE_INSTANCE, PIPE_ACCESS_DUPLEX, SECURITY_IDENTIFICATION,
        SECURITY_SQOS_PRESENT,
    },
    System::Pipes::{
        ConnectNamedPipe, CreateNamedPipeW, DisconnectNamedPipe, PIPE_REJECT_REMOTE_CLIENTS,
    },
};

fn path(endpoint: &str) -> io::Result<String> {
    if endpoint.is_empty()
        || endpoint.len() > 80
        || !endpoint
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(&b))
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "Invalid local Synapse endpoint",
        ));
    }
    Ok(format!(r"\\.\pipe\Synapse-0.3-{endpoint}"))
}

pub fn connect(endpoint: &str) -> io::Result<File> {
    let expected_owner = owner_sid().map_err(io::Error::other)?;
    let stream = OpenOptions::new()
        .read(true)
        .write(true)
        .custom_flags(SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION)
        .open(path(endpoint)?)?;
    let mut owner = null_mut();
    let mut descriptor = null_mut();
    // GetSecurityInfo allocates the descriptor containing the owner SID.
    let status = unsafe {
        GetSecurityInfo(
            stream.as_raw_handle(),
            SE_FILE_OBJECT,
            OWNER_SECURITY_INFORMATION,
            &mut owner,
            null_mut(),
            null_mut(),
            null_mut(),
            &mut descriptor,
        )
    };
    if status != 0 {
        return Err(io::Error::from_raw_os_error(status as i32));
    }
    let actual_owner = sid_text(owner);
    unsafe {
        LocalFree(descriptor);
    }
    if actual_owner.map_err(io::Error::other)? != expected_owner {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Local Synapse endpoint has a different owner",
        ));
    }
    Ok(stream)
}

pub struct Listener(File);

impl Listener {
    pub fn bind(endpoint: &str) -> io::Result<Self> {
        let name: Vec<_> = path(endpoint)?.encode_utf16().chain(Some(0)).collect();
        let owner = owner_sid().map_err(io::Error::other)?;
        let acl: Vec<_> = format!("O:{owner}D:P(A;;GA;;;{owner})")
            .encode_utf16()
            .chain(Some(0))
            .collect();
        let mut descriptor = null_mut();
        if unsafe {
            ConvertStringSecurityDescriptorToSecurityDescriptorW(
                acl.as_ptr(),
                1,
                &mut descriptor,
                null_mut(),
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        let attributes = SECURITY_ATTRIBUTES {
            nLength: size_of::<SECURITY_ATTRIBUTES>() as u32,
            lpSecurityDescriptor: descriptor,
            bInheritHandle: 0,
        };
        // Keep this exclusive, local-only instance open across client reconnects.
        let handle = unsafe {
            CreateNamedPipeW(
                name.as_ptr(),
                PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE,
                PIPE_REJECT_REMOTE_CLIENTS,
                1,
                65536,
                65536,
                0,
                &attributes,
            )
        };
        let failure = (handle == INVALID_HANDLE_VALUE).then(io::Error::last_os_error);
        unsafe {
            LocalFree(descriptor);
        }
        match failure {
            Some(error) => Err(error),
            None => Ok(Self(unsafe { File::from_raw_handle(handle) })),
        }
    }

    pub fn accept(&self) -> io::Result<Session<'_>> {
        loop {
            if unsafe { ConnectNamedPipe(self.0.as_raw_handle(), null_mut()) } != 0 {
                return Ok(Session(&self.0));
            }
            let error = io::Error::last_os_error();
            match error.raw_os_error().map(|code| code as u32) {
                Some(ERROR_PIPE_CONNECTED) => return Ok(Session(&self.0)),
                Some(ERROR_NO_DATA) => unsafe {
                    DisconnectNamedPipe(self.0.as_raw_handle());
                },
                _ => return Err(error),
            }
        }
    }
}

pub struct Session<'a>(pub &'a File);

impl Drop for Session<'_> {
    fn drop(&mut self) {
        unsafe {
            DisconnectNamedPipe(self.0.as_raw_handle());
        }
    }
}

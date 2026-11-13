//! Windows notification icon for an explicitly enabled background Presence.
use std::{
    io,
    mem::size_of,
    ptr::{null, null_mut},
    sync::mpsc::{self, Receiver, SyncSender},
    thread::{self, JoinHandle},
};

use windows_sys::Win32::{
    Foundation::{HWND, LPARAM, LRESULT, POINT, WPARAM},
    System::LibraryLoader::GetModuleHandleW,
    UI::{
        Shell::{
            NIF_ICON, NIF_MESSAGE, NIF_SHOWTIP, NIF_TIP, NIM_ADD, NIM_DELETE, NIM_SETVERSION,
            NIN_SELECT, NINF_KEY, NOTIFYICON_VERSION_4, NOTIFYICONDATAW, Shell_NotifyIconW,
        },
        WindowsAndMessaging::{
            AppendMenuW, CREATESTRUCTW, CreatePopupMenu, CreateWindowExW, DefWindowProcW,
            DestroyMenu, DestroyWindow, DispatchMessageW, EndMenu, GWLP_USERDATA, GetCursorPos,
            GetMessageW, GetWindowLongPtrW, IDI_APPLICATION, IsWindow, LoadIconW, MF_STRING, MSG,
            PostMessageW, PostQuitMessage, RegisterClassW, RegisterWindowMessageW,
            SetForegroundWindow, SetWindowLongPtrW, TPM_NONOTIFY, TPM_RETURNCMD, TPM_RIGHTBUTTON,
            TrackPopupMenu, TranslateMessage, UnregisterClassW, WM_APP, WM_CLOSE, WM_CONTEXTMENU,
            WM_DESTROY, WM_NCCREATE, WM_NULL, WNDCLASSW,
        },
    },
};

const TRAY_MESSAGE: u32 = WM_APP + 1;
const NIN_KEYSELECT: u32 = NIN_SELECT | NINF_KEY;
const OPEN: usize = 1;
const MUTE: usize = 2;
const EXIT: usize = 3;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Event {
    Open,
    Mute,
    Exit,
}

pub struct Tray {
    window: usize,
    events: Receiver<Event>,
    worker: Option<JoinHandle<()>>,
}

impl Tray {
    #[cfg(test)]
    fn new() -> Result<Self, String> {
        Self::with_wakeup(|| {})
    }

    pub fn with_wakeup(wake: impl Fn() + Send + 'static) -> Result<Self, String> {
        let (events_send, events) = mpsc::sync_channel(8);
        let (ready, start) = mpsc::sync_channel(1);
        let worker = thread::spawn(move || run(events_send, ready, Box::new(wake)));
        match start.recv() {
            Ok(Ok(window)) => Ok(Self {
                window,
                events,
                worker: Some(worker),
            }),
            result => {
                let _ = worker.join();
                Err(result
                    .ok()
                    .and_then(Result::err)
                    .unwrap_or_else(|| "A área de notificação não iniciou.".into()))
            }
        }
    }

    pub fn take_event(&self) -> Option<Event> {
        self.events.try_recv().ok()
    }
}

impl Drop for Tray {
    fn drop(&mut self) {
        unsafe { PostMessageW(self.window as HWND, WM_CLOSE, 0, 0) };
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}

struct TrayWindow {
    events: SyncSender<Event>,
    taskbar_created: u32,
    wake: Box<dyn Fn() + Send>,
}

impl TrayWindow {
    fn send(&self, event: Event) {
        if self.events.try_send(event).is_ok() {
            (self.wake)();
        }
    }
}

fn wide(text: &str) -> Vec<u16> {
    text.encode_utf16().chain([0]).collect()
}

fn run(
    events: SyncSender<Event>,
    ready: SyncSender<Result<usize, String>>,
    wake: Box<dyn Fn() + Send>,
) {
    let class = wide("SynapsePresenceTray");
    let title = wide("Synapse Presence");
    let instance = unsafe { GetModuleHandleW(null()) };
    let registration = WNDCLASSW {
        lpfnWndProc: Some(window_proc),
        hInstance: instance,
        lpszClassName: class.as_ptr(),
        ..Default::default()
    };
    if unsafe { RegisterClassW(&registration) } == 0 {
        let _ = ready.send(Err(io::Error::last_os_error().to_string()));
        return;
    }
    let window_state = TrayWindow {
        events,
        wake,
        taskbar_created: unsafe { RegisterWindowMessageW(wide("TaskbarCreated").as_ptr()) },
    };
    let window = unsafe {
        CreateWindowExW(
            0,
            class.as_ptr(),
            title.as_ptr(),
            0,
            0,
            0,
            0,
            0,
            null_mut(),
            null_mut(),
            instance,
            (&raw const window_state).cast(),
        )
    };
    if window.is_null() || !install(window) {
        let _ = ready.send(Err(
            "Não foi possível exibir os controles do Presence na área de notificação.".into(),
        ));
        if !window.is_null() {
            unsafe { DestroyWindow(window) };
        }
    } else if ready.send(Ok(window as usize)).is_ok() {
        let mut message = MSG::default();
        while unsafe { GetMessageW(&mut message, null_mut(), 0, 0) } > 0 {
            unsafe {
                TranslateMessage(&message);
                DispatchMessageW(&message);
            }
        }
    } else {
        unsafe { DestroyWindow(window) };
    }
    if !window.is_null() && unsafe { IsWindow(window) } != 0 {
        unsafe { DestroyWindow(window) };
    }
    unsafe { UnregisterClassW(class.as_ptr(), instance) };
}

fn icon(window: HWND) -> NOTIFYICONDATAW {
    NOTIFYICONDATAW {
        cbSize: size_of::<NOTIFYICONDATAW>() as u32,
        hWnd: window,
        uID: 1,
        ..Default::default()
    }
}

fn install(window: HWND) -> bool {
    let mut data = icon(window);
    data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP;
    data.uCallbackMessage = TRAY_MESSAGE;
    data.hIcon = unsafe { LoadIconW(null_mut(), IDI_APPLICATION) };
    let label = wide("Synapse Presence · Controles de áudio");
    data.szTip[..label.len()].copy_from_slice(&label);
    if unsafe { Shell_NotifyIconW(NIM_ADD, &data) } == 0 {
        return false;
    }
    data.Anonymous.uVersion = NOTIFYICON_VERSION_4;
    if unsafe { Shell_NotifyIconW(NIM_SETVERSION, &data) } == 0 {
        unsafe { Shell_NotifyIconW(NIM_DELETE, &data) };
        return false;
    }
    true
}

unsafe extern "system" fn window_proc(
    window: HWND,
    message: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    if message == WM_NCCREATE {
        let create = unsafe { &*(lparam as *const CREATESTRUCTW) };
        unsafe { SetWindowLongPtrW(window, GWLP_USERDATA, create.lpCreateParams as isize) };
    }
    let context = unsafe { GetWindowLongPtrW(window, GWLP_USERDATA) } as *const TrayWindow;
    if let Some(context) = unsafe { context.as_ref() } {
        if message == TRAY_MESSAGE {
            let event = match (lparam as u32) & 0xffff {
                WM_CONTEXTMENU => menu(window),
                NIN_SELECT | NIN_KEYSELECT => Some(Event::Open),
                _ => None,
            };
            if let Some(event) = event {
                context.send(event);
            }
            return 0;
        }
        if context.taskbar_created != 0 && message == context.taskbar_created {
            if !install(window) {
                context.send(Event::Open);
            }
            return 0;
        }
    }
    match message {
        WM_CLOSE => {
            unsafe {
                EndMenu();
                DestroyWindow(window);
            }
            0
        }
        WM_DESTROY => {
            unsafe {
                Shell_NotifyIconW(NIM_DELETE, &icon(window));
                PostQuitMessage(0);
            }
            0
        }
        _ => unsafe { DefWindowProcW(window, message, wparam, lparam) },
    }
}

fn menu(window: HWND) -> Option<Event> {
    let menu = unsafe { CreatePopupMenu() };
    if menu.is_null() {
        return None;
    }
    for (id, label) in [
        (OPEN, "Abrir Presence"),
        (MUTE, "Silenciar microfone"),
        (EXIT, "Sair do Synapse"),
    ] {
        if unsafe { AppendMenuW(menu, MF_STRING, id, wide(label).as_ptr()) } == 0 {
            unsafe { DestroyMenu(menu) };
            return None;
        }
    }
    let mut point = POINT::default();
    unsafe {
        GetCursorPos(&mut point);
        SetForegroundWindow(window);
    }
    let selection = unsafe {
        TrackPopupMenu(
            menu,
            TPM_RETURNCMD | TPM_NONOTIFY | TPM_RIGHTBUTTON,
            point.x,
            point.y,
            0,
            window,
            null(),
        )
    } as usize;
    unsafe {
        PostMessageW(window, WM_NULL, 0, 0);
        DestroyMenu(menu);
    }
    selection_event(selection)
}

fn selection_event(selection: usize) -> Option<Event> {
    match selection {
        OPEN => Some(Event::Open),
        MUTE => Some(Event::Mute),
        EXIT => Some(Event::Exit),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{Duration, Instant};

    #[test]
    fn menu_commands_map_to_visible_controls() {
        assert_eq!(selection_event(OPEN), Some(Event::Open));
        assert_eq!(selection_event(MUTE), Some(Event::Mute));
        assert_eq!(selection_event(EXIT), Some(Event::Exit));
        assert_eq!(selection_event(0), None);
    }

    #[test]
    #[ignore = "requires the Windows interactive notification area"]
    fn native_tray_registers_dispatches_and_releases() {
        let tray = Tray::new().unwrap();
        let window = tray.window as HWND;
        assert_ne!(unsafe { IsWindow(window) }, 0);
        assert_ne!(
            unsafe { PostMessageW(window, TRAY_MESSAGE, 0, NIN_KEYSELECT as LPARAM) },
            0
        );
        let deadline = Instant::now() + Duration::from_secs(2);
        loop {
            if let Some(event) = tray.take_event() {
                assert_eq!(event, Event::Open);
                break;
            }
            assert!(
                Instant::now() < deadline,
                "Notification event did not arrive"
            );
            thread::sleep(Duration::from_millis(10));
        }
        drop(tray);
        assert_eq!(unsafe { IsWindow(window) }, 0);
    }
}

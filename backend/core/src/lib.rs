pub mod browser_analysis;
pub mod browser_image;
pub mod browser_policy;
mod candidate;
mod chats;
mod checks;
mod context;
pub mod contracts;
mod conversation;
mod core;
mod git_workspace;
mod integration;
mod learning;
#[cfg(windows)]
pub mod local_pipe;
mod memory;
mod mission_recovery;
mod mission_run;
mod missions;
mod planner;
mod projects;
mod registry;
mod runner;
mod skills;
mod store;
mod tools;
mod voice;
mod worker;
pub use contracts::{Command, CoreError, CoreResult, Request, Response};
pub use core::Core;

/// Resolve the Python package from the installed distribution first.
pub fn python_package_root(development: &std::path::Path) -> std::io::Result<std::path::PathBuf> {
    let bundled = std::env::current_exe()?.with_file_name("python");
    if bundled.exists() {
        if !bundled.join("synapse_ai/__init__.py").is_file() {
            return Err(std::io::Error::other(
                "The bundled Python package is incomplete",
            ));
        }
        return bundled.canonicalize();
    }
    development.canonicalize()
}

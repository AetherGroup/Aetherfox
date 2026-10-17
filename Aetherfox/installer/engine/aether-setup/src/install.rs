//! Install flow shared by the CLI and the GUI.
use std::path::{Path, PathBuf};

use crate::{reg, shortcuts};

pub const DEFAULT_DIR: &str = r"C:\Program Files\Aether Browser";

pub struct Options {
    pub dir: String,
    pub lang: String,
    pub desktop_icon: bool,
}

pub fn run(opts: &Options, progress: &dyn Fn(u64, u64)) -> Result<(), String> {
    let dir = Path::new(&opts.dir);
    // 1. payload (sidecar o anexado).
    let payload = crate::locate_payload()?;
    // 2. extract (strip a single root dir).
    crate::extract_zip(&payload, dir, progress);
    // 3. local uninstaller (a copy of this exe).
    let udir = dir.join("uninstall");
    std::fs::create_dir_all(&udir).map_err(|e| e.to_string())?;
    let me = std::env::current_exe().map_err(|e| e.to_string())?;
    std::fs::copy(&me, udir.join("uninstall.exe")).map_err(|e| e.to_string())?;
    // 4. registro.
    reg::write_uninstall(reg::machine_hive(), &opts.dir,
                         env!("CARGO_PKG_VERSION"));
    // 5. accesos directos.
    let target = dir.join("aether.exe");
    let t = target.to_string_lossy().to_string();
    if opts.desktop_icon {
        if let Some(d) = shortcuts::desktop_dir() {
            shortcuts::create_lnk(&t, &(d + "\\Aether Browser.lnk"),
                                  "Aether Browser", &t)?;
        }
    }
    let startm = std::env::var("ProgramData")
        .unwrap_or("C:\\ProgramData".into())
        + "\\Microsoft\\Windows\\Start Menu\\Programs\\Aether Browser";
    std::fs::create_dir_all(&startm).map_err(|e| e.to_string())?;
    shortcuts::create_lnk(&t, &(startm + "\\Aether Browser.lnk"),
                          "Aether Browser", &t)?;
    let _ = &opts.lang; // langpacks (engine v2): for now en-US only.
    Ok(())
}

pub fn open_browser(dir: &str) {
    let _ = std::process::Command::new(Path::new(dir).join("aether.exe"))
        .spawn();
}

#[allow(dead_code)]
pub fn exe_path() -> PathBuf {
    std::env::current_exe().unwrap_or(Path::new(".").to_path_buf())
}

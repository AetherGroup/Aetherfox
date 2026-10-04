//! Aether Setup v1 (esqueleto): instalador propio en Rust + windows-rs.
//! Today: CLI + step flow (no real actions yet). The visual mock
//! (installer/mock-installer.ps1) is the UI spec to port.

use std::env;

mod install;
mod reg;
mod shortcuts;
mod ui;

const VERSION: &str = env!("CARGO_PKG_VERSION");

fn usage() -> ! {
    println!("aether-setup {VERSION}");
    println!("Uso:");
    println!("  aether-setup --install [--dir <ruta>] [--lang <id>] [--desktop-icon|--no-desktop-icon]");
    println!("  aether-setup --uninstall");
    println!("  aether-setup --version");
    println!("  aether-setup [--gui]  (interfaz grafica)");
    std::process::exit(2);
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.is_empty() || args[0] == "--gui" {
        ui::run();
        return;
    }
    match args[0].as_str() {
        "--version" => println!("aether-setup {VERSION}"),
        "--install" => cmd_install(&args[1..]),
        "--uninstall" => cmd_uninstall(),
        _ => usage(),
    }
}

fn cmd_install(args: &[String]) {
    let mut dir = r"C:\Program Files\Aether Browser".to_string();
    let mut lang = "en-US".to_string();
    let mut desktop_icon = true;
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--dir" => {
                i += 1;
                dir = args.get(i).cloned().unwrap_or(dir);
            }
            "--lang" => {
                i += 1;
                lang = args.get(i).cloned().unwrap_or(lang);
            }
            "--desktop-icon" => desktop_icon = true,
            "--no-desktop-icon" => desktop_icon = false,
            _ => usage(),
        }
        i += 1;
    }
    let opts = install::Options { dir, lang, desktop_icon };
    match install::run(&opts, &|done, total| {
        if total > 0 {
            print!("\r    {} / {} MB", done / 1_048_576, total / 1_048_576);
        }
    }) {
        Ok(()) => println!("\nOK"),
        Err(e) => {
            eprintln!("error: {e}");
            std::process::exit(1);
        }
    }
}

/// Locates the payload: a `<exe>.payload.zip` sidecar next to the binary,
/// or appended to the exe itself (u64 LE footer with the offset, see make-installer.py).
pub(crate) fn locate_payload() -> Result<std::path::PathBuf, String> {
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    // Sidecar: <exe>.payload.zip next to the binary.
    let mut s = exe.as_os_str().to_owned();
    s.push(".payload.zip");
    let sidecar = std::path::PathBuf::from(s);
    if sidecar.is_file() {
        return Ok(sidecar);
    }
    // Appended: the last 8 bytes LE are the zip offset inside the exe.
    let data = std::fs::read(&exe).map_err(|e| e.to_string())?;
    if data.len() < 8 {
        return Err("exe has no payload (neither sidecar nor appended)".into());
    }
    let off = u64::from_le_bytes(data[data.len() - 8..].try_into().unwrap());
    if off == 0 || off as usize >= data.len() {
        return Err("no payload (use --sidecar or package it with make-installer.py)".into());
    }
    // Write it out to a temp file for the zip (avoids SliceReader lifetimes).
    let tmp = std::env::temp_dir().join("aether-payload.zip");
    std::fs::write(&tmp, &data[off as usize..data.len() - 8])
        .map_err(|e| e.to_string())?;
    Ok(tmp)
}

pub(crate) fn extract_zip(src: &std::path::Path, dst: &std::path::Path,
               mut progress: impl FnMut(u64, u64)) {
    let f = std::fs::File::open(src).unwrap();
    let total_uncomp: u64 = {
        let mut z = zip::ZipArchive::new(&f).unwrap();
        (0..z.len()).map(|i| z.by_index(i).unwrap().size()).sum()
    };
    let mut z = zip::ZipArchive::new(f).unwrap();
    // If everything hangs off a single root dir (our portable zip),
    // strip it so the contents install into the destination.
    let mut root: Option<String> = None;
    let mut multi = false;
    for i in 0..z.len() {
        let n = z.by_index(i).unwrap().name().replace('\\', "/");
        let top = n.split('/').next().unwrap_or("").to_string();
        match &root {
            None => root = Some(top),
            Some(r) if *r == top => {}
            _ => {
                multi = true;
                break;
            }
        }
    }
    let strip = if multi { 0 } else { 1 };
    let mut done: u64 = 0;
    for i in 0..z.len() {
        let mut file = z.by_index(i).unwrap();
        let rel: std::path::PathBuf = file.name().replace('\\', "/")
            .split('/').skip(strip).collect();
        if rel.as_os_str().is_empty() {
            continue;
        }
        let out = dst.join(rel);
        if file.is_dir() {
            std::fs::create_dir_all(&out).unwrap();
        } else {
            if let Some(p) = out.parent() {
                std::fs::create_dir_all(p).unwrap();
            }
            let mut w = std::fs::File::create(&out).unwrap();
            std::io::copy(&mut file, &mut w).unwrap();
            done += file.size();
            progress(done, total_uncomp);
        }
    }
}

fn cmd_uninstall() {
    use std::os::windows::ffi::OsStrExt;
    let me = std::env::current_exe().unwrap();
    // The uninstaller lives in <dir>\uninstall\: that dir is its parent.
    let dir = me.parent().and_then(|p| p.parent()).unwrap().to_path_buf();
    let ds = dir.to_string_lossy().to_string();
    println!("[1/2] accesos directos + registro en {ds}...");
    if let Some(d) = shortcuts::desktop_dir() {
        let _ = std::fs::remove_file(format!("{d}\\Aether Browser.lnk"));
    }
    let startm = std::env::var("ProgramData").unwrap_or("C:\\ProgramData".into())
        + "\\Microsoft\\Windows\\Start Menu\\Programs\\Aether Browser";
    let _ = std::fs::remove_file(format!("{startm}\\Aether Browser.lnk"));
    let _ = std::fs::remove_dir(&startm);
    reg::remove_uninstall(reg::machine_hive());
    println!("[2/2] files (the exe deletes itself on reboot)...");
    let me_s = me.to_string_lossy().to_string();
    for e in walkdir(&dir) {
        if e == me_s {
            continue;
        }
        let p = std::path::Path::new(&e);
        if p.is_dir() {
            let _ = std::fs::remove_dir_all(&e);
        } else {
            let _ = std::fs::remove_file(&e);
        }
    }
    // Self-delete on reboot (file + folder).
    use windows_sys::Win32::Storage::FileSystem::{
        MoveFileExW, MOVEFILE_DELAY_UNTIL_REBOOT,
    };
    let w = |s: &str| {
        std::ffi::OsStr::new(s).encode_wide().chain([0]).collect::<Vec<u16>>()
    };
    unsafe {
        MoveFileExW(w(&me_s).as_ptr(), std::ptr::null(),
                    MOVEFILE_DELAY_UNTIL_REBOOT);
        MoveFileExW(w(&ds).as_ptr(), std::ptr::null(),
                    MOVEFILE_DELAY_UNTIL_REBOOT);
    }
    println!("OK (reboot pending for the rest)");
}

fn walkdir(root: &std::path::Path) -> Vec<String> {
    let mut out = vec![];
    let mut stack = vec![root.to_path_buf()];
    while let Some(d) = stack.pop() {
        let rd = match std::fs::read_dir(&d) {
            Ok(r) => r,
            Err(_) => continue,
        };
        for e in rd.flatten() {
            let p = e.path();
            if p.is_dir() {
                stack.push(p.clone());
            }
            out.push(p.to_string_lossy().to_string());
        }
    }
    out
}

//! Accesos directos (.lnk) via IShellLinkW manual (windows-sys 0.61
//! does not ship COM interfaces: vtable by hand). No dependencies.
use std::ffi::{OsStr, c_void};
use std::os::windows::ffi::OsStrExt;

use windows_sys::Win32::System::Com::{
    CLSCTX_INPROC_SERVER, COINIT_APARTMENTTHREADED, CoCreateInstance,
    CoInitializeEx, CoUninitialize,
};
use windows_sys::Win32::UI::Shell::{CSIDL_DESKTOPDIRECTORY, SHGetFolderPathW};
use windows_sys::core::GUID;

const CLSID_SHELL_LINK: GUID = GUID::from_u128(0x00021401_0000_0000_c000_000000000046);
const IID_ISHELL_LINK_W: GUID =
    GUID::from_u128(0x000214F9_0000_0000_c000_000000000046);
const IID_IPERSIST_FILE: GUID =
    GUID::from_u128(0x0000010b_0000_0000_c000_000000000046);

/// Prefijos IUnknown (0-2) + IShellLinkW hasta SetPath (20).
#[repr(C)]
struct ShellLinkVtbl {
    query_interface: unsafe extern "system" fn(*mut c_void, *const GUID, *mut *mut c_void) -> i32,
    _ar: unsafe extern "system" fn(*mut c_void) -> u32,
    _rel: unsafe extern "system" fn(*mut c_void) -> u32,
    _p03: usize, _p04: usize, _p05: usize, _p06: usize,
    set_description: unsafe extern "system" fn(*mut c_void, *const u16) -> i32,
    _p08: usize, _p09: usize, _p10: usize, _p11: usize, _p12: usize,
    _p13: usize, _p14: usize, _p15: usize, _p16: usize,
    set_icon_location: unsafe extern "system" fn(*mut c_void, *const u16, i32) -> i32,
    _p18: usize, _p19: usize,
    set_path: unsafe extern "system" fn(*mut c_void, *const u16) -> i32,
}

/// IPersistFile vtable (only what is used + the gaps up to Save).
#[repr(C)]
struct PersistVtbl {
    _qi: unsafe extern "system" fn(*mut c_void, *const GUID, *mut *mut c_void) -> i32,
    _ar: unsafe extern "system" fn(*mut c_void) -> u32,
    _rel: unsafe extern "system" fn(*mut c_void) -> u32,
    _getid: unsafe extern "system" fn(*mut c_void, *mut GUID) -> i32,
    _dirty: unsafe extern "system" fn(*mut c_void) -> i32,
    _load: usize,
    save: unsafe extern "system" fn(*mut c_void, *const u16, i32) -> i32,
}

fn wide(s: &str) -> Vec<u16> {
    OsStr::new(s).encode_wide().chain([0]).collect()
}

pub fn create_lnk(target: &str, link_path: &str, desc: &str,
                  icon: &str) -> Result<(), String> {
    unsafe {
        let hr = CoInitializeEx(std::ptr::null_mut(),
                                COINIT_APARTMENTTHREADED as u32);
        if hr != 0 && hr != 1 {
            return Err(format!("CoInitializeEx: {hr:#x}"));
        }
        let r: Result<(), String> = (|| {
            let mut link: *mut c_void = std::ptr::null_mut();
            let hr = CoCreateInstance(
                &CLSID_SHELL_LINK,
                std::ptr::null_mut(),
                CLSCTX_INPROC_SERVER,
                &IID_ISHELL_LINK_W,
                &mut link,
            );
            if hr != 0 || link.is_null() {
                return Err(format!("CoCreateInstance: {hr:#x}"));
            }
            let vt = *(link as *const *const ShellLinkVtbl);
            let t = wide(target);
            let d = wide(desc);
            let ic = wide(icon);
            if ((*vt).set_description)(link, d.as_ptr()) != 0 {
                return Err("SetDescription".into());
            }
            if ((*vt).set_icon_location)(link, ic.as_ptr(), 0) != 0 {
                return Err("SetIconLocation".into());
            }
            if ((*vt).set_path)(link, t.as_ptr()) != 0 {
                return Err("SetPath".into());
            }
            // IPersistFile::Save (index 6) to save the .lnk.
            let mut pf: *mut c_void = std::ptr::null_mut();
            type QiFn = unsafe extern "system" fn(
                *mut c_void, *const GUID, *mut *mut c_void) -> i32;
            let qi = *(link as *const *const QiFn);
            if (*qi)(link, &IID_IPERSIST_FILE, &mut pf) != 0
                || pf.is_null()
            {
                return Err("QueryInterface IPersistFile".into());
            }
            // IPersistFile::Save via vtable completa (indice 6).
            let pv = *(pf as *const *const PersistVtbl);
            let lp = wide(link_path);
            if ((*pv).save)(pf, lp.as_ptr(), 1) != 0 {
                return Err("IPersistFile::Save".into());
            }
            Ok(())
        })();
        CoUninitialize();
        r
    }
}

pub fn desktop_dir() -> Option<String> {    unsafe {
        let mut buf = [0u16; 260];
        if SHGetFolderPathW(std::ptr::null_mut(), CSIDL_DESKTOPDIRECTORY as i32,
                            std::ptr::null_mut(), 0, buf.as_mut_ptr()) == 0
        {
            let n = buf.iter().position(|&c| c == 0).unwrap_or(buf.len());
            return Some(String::from_utf16_lossy(&buf[..n]));
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cocreate_only() {
        unsafe {
            assert_eq!(CoInitializeEx(std::ptr::null_mut(),
                                      COINIT_APARTMENTTHREADED as u32), 0);
            let mut link: *mut c_void = std::ptr::null_mut();
            let hr = CoCreateInstance(
                &CLSID_SHELL_LINK,
                std::ptr::null_mut(),
                CLSCTX_INPROC_SERVER,
                &IID_ISHELL_LINK_W,
                &mut link,
            );
            assert_eq!(hr, 0);
            assert!(!link.is_null());
            CoUninitialize();
        }
    }

    #[test]
    fn create_and_read_back_lnk() {
        let dir = std::env::temp_dir().join("aether-lnk-test");
        std::fs::create_dir_all(&dir).unwrap();
        let link = dir.join("probe.lnk");
        let _ = std::fs::remove_file(&link);
        create_lnk(r"C:\Windows\System32\notepad.exe",
                   link.to_str().unwrap(), "Probe",
                   r"C:\Windows\System32\notepad.exe").unwrap();
        let meta = std::fs::metadata(&link).unwrap();
        assert!(meta.len() > 100, "lnk sospechosamente pequeño");
        // The target must be inside the .lnk binary.
        let raw = std::fs::read(&link).unwrap();
        let needle: Vec<u16> = "notepad.exe\0".encode_utf16().collect();
        let hay: Vec<u8> = needle.iter().flat_map(|c| c.to_le_bytes()).collect();
        assert!(raw.windows(hay.len()).any(|w| w == hay.as_slice()));
        std::fs::remove_dir_all(&dir).unwrap();
    }
}

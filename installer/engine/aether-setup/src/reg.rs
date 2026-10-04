//! Windows registry access for the installer (hive is parameterisable for tests).
use std::ffi::OsStr;
use std::os::windows::ffi::OsStrExt;

use windows_sys::Win32::Foundation::ERROR_SUCCESS;
use windows_sys::Win32::System::Registry::{
    HKEY, HKEY_LOCAL_MACHINE, KEY_SET_VALUE, REG_SZ,
    RegCloseKey, RegCreateKeyExW, RegDeleteKeyExW, RegDeleteTreeW,
    RegSetValueExW,
};

pub const UNINSTALL_SUBKEY: &str =
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Aether Browser";

fn wide(s: &str) -> Vec<u16> {
    OsStr::new(s).encode_wide().chain([0]).collect()
}

fn open_or_create(hive: HKEY, subkey: &str) -> Result<HKEY, u32> {
    let mut h: HKEY = std::ptr::null_mut();
    let rc = unsafe {
        RegCreateKeyExW(hive, wide(subkey).as_ptr(), 0, std::ptr::null(), 0,
                        KEY_SET_VALUE, std::ptr::null(), &mut h,
                        std::ptr::null_mut())
    };
    if rc == ERROR_SUCCESS { Ok(h) } else { Err(rc) }
}

fn set_sz(h: HKEY, name: &str, value: &str) {
    let v = wide(value);
    let rc = unsafe {
        RegSetValueExW(h, wide(name).as_ptr(), 0, REG_SZ,
                       v.as_ptr() as *const u8, (v.len() * 2) as u32)
    };
    assert_eq!(rc, ERROR_SUCCESS, "RegSetValueExW {name}");
}

pub fn write_uninstall(hive: HKEY, dir: &str, version: &str) {
    let h = open_or_create(hive, UNINSTALL_SUBKEY).unwrap();
    set_sz(h, "DisplayName", "Aether Browser");
    set_sz(h, "DisplayVersion", version);
    set_sz(h, "InstallLocation", dir);
    set_sz(h, "DisplayIcon", &format!("{dir}\\aether.exe"));
    set_sz(h, "UninstallString",
           &format!("\"{dir}\\uninstall\\uninstall.exe\""));
    set_sz(h, "NoModify", "1");
    set_sz(h, "NoRepair", "1");
    unsafe { RegCloseKey(h) };
}

pub fn remove_uninstall(hive: HKEY) {
    unsafe {
        // Borra subclave entera; si no existe, exito silencioso.
        let rc = RegDeleteTreeW(hive, wide(UNINSTALL_SUBKEY).as_ptr());
        if rc != ERROR_SUCCESS {
            let _ = RegDeleteKeyExW(hive, wide(UNINSTALL_SUBKEY).as_ptr(),
                                    0, 0);
        }
    }
}

#[allow(dead_code)]
pub fn machine_hive() -> HKEY {
    HKEY_LOCAL_MACHINE
}

#[cfg(test)]
mod tests {
    use super::*;
    use windows_sys::Win32::System::Registry::{
        HKEY_CURRENT_USER, KEY_READ, RRF_RT_REG_SZ, RegGetValueW, RegOpenKeyExW,
    };

    const TKEY: &str = r"SOFTWARE\AetherSetupTest";

    fn read_sz(hive: HKEY, sub: &str, name: &str) -> String {
        let mut buf = [0u16; 260];
        let mut len = (buf.len() * 2) as u32;
        let rc = unsafe {
            RegGetValueW(hive, wide(sub).as_ptr(), wide(name).as_ptr(),
                         RRF_RT_REG_SZ, std::ptr::null_mut(),
                         buf.as_mut_ptr() as *mut _, &mut len)
        };
        assert_eq!(rc, ERROR_SUCCESS);
        String::from_utf16_lossy(&buf[..(len as usize / 2).saturating_sub(1)])
    }

    #[test]
    fn roundtrip_uninstall_key() {
        let h = open_or_create(HKEY_CURRENT_USER, TKEY).unwrap();
        set_sz(h, "DisplayName", "Aether Browser");
        unsafe { RegCloseKey(h) };
        assert_eq!(read_sz(HKEY_CURRENT_USER, TKEY, "DisplayName"),
                   "Aether Browser");
        unsafe {
            RegDeleteTreeW(HKEY_CURRENT_USER, wide(TKEY).as_ptr());
        }
    }

    #[test]
    fn write_remove_uninstall_real_shape() {
        write_uninstall(HKEY_CURRENT_USER, r"C:\Aether", "0.1");
        let v = read_sz(HKEY_CURRENT_USER, UNINSTALL_SUBKEY, "DisplayVersion");
        assert_eq!(v, "0.1");
        remove_uninstall(HKEY_CURRENT_USER);
        let mut h: HKEY = std::ptr::null_mut();
        let rc = unsafe {
            RegOpenKeyExW(HKEY_CURRENT_USER, wide(UNINSTALL_SUBKEY).as_ptr(),
                          0, KEY_READ, &mut h)
        };
        assert_ne!(rc, ERROR_SUCCESS);
    }
}

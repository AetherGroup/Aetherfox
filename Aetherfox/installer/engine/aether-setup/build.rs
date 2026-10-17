//! Incrusta app.manifest via rc.exe localizado explicitamente.
//! (embed-resource did not locate the SDK reliably on this machine.)
use std::path::{Path, PathBuf};
use std::process::Command;

fn find_rc() -> Option<PathBuf> {
    let mut cands = vec![];
    if let Ok(p) = std::env::var("PATH") {
        for d in std::env::split_paths(&p) {
            cands.push(Path::new(&d).join("rc.exe"));
        }
    }
    for k in [
        r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\rc.exe",
        r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.28000.0\x64\rc.exe",
    ] {
        cands.push(PathBuf::from(k));
    }
    if let Ok(vs) = std::env::var("WindowsSdkDir") {
        cands.push(Path::new(&vs).join(r"bin\x64\rc.exe"));
    }
    cands.into_iter().find(|p| p.is_file())
}

fn main() {
    println!("cargo:rerun-if-changed=app.manifest");
    // UAC manifest only in release: in dev/test it would block execution
    // (elevation) y `cargo test` no podria ni arrancar.
    if std::env::var("PROFILE").as_deref() != Ok("release") {
        return;
    }
    let manifest = Path::new(env!("CARGO_MANIFEST_DIR")).join("app.manifest");
    let rc = find_rc().expect("rc.exe no encontrado (Windows SDK)");
    // rc reads C-style escapes (\a = bell): double the backslashes.
    let shown = manifest.display().to_string().replace('\\', "\\\\");
    let rc_src = format!("1 24 \"{}\"\n", shown);
    let out = Path::new(&std::env::var("OUT_DIR").unwrap()).join("app.rc");
    std::fs::write(&out, rc_src).unwrap();
    let res = out.with_extension("res");
    let outp = Command::new(&rc)
        .arg("/nologo")
        .arg("/fo")
        .arg(&res)
        .arg(&out)
        .output()
        .expect("ejecutar rc.exe");
    if !outp.status.success() {
        panic!(
            "rc.exe fallo:\nstdout: {}\nstderr: {}",
            String::from_utf8_lossy(&outp.stdout),
            String::from_utf8_lossy(&outp.stderr)
        );
    }
    println!("cargo:rustc-link-arg={}", res.display());
    println!("cargo:warning=manifest-res={}", res.display());
}

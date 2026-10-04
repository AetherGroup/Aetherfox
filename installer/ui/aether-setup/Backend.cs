using System;
using System.IO;
using System.IO.Compression;
using Microsoft.Win32;

namespace AetherSetup
{
    public enum Scope { User, System }

    public record Options(string Dir, string Lang, bool DesktopIcon,
                          Scope Scope = Scope.User);

    public static class Backend
    {
        public const string SystemDir = @"C:\Program Files\Aether Browser";
        public static string UserDir => Path.Combine(
            Environment.GetFolderPath(
                Environment.SpecialFolder.LocalApplicationData),
            "Aether Browser");
        private const string UnkeyPath =
            @"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Aether Browser";

        private static RegistryKey Hive(Scope s) =>
            s == Scope.System ? Registry.LocalMachine : Registry.CurrentUser;

        public static bool IsElevated() =>
            new System.Security.Principal.WindowsPrincipal(
                System.Security.Principal.WindowsIdentity.GetCurrent())
            .IsInRole(System.Security.Principal.WindowsBuiltInRole.Administrator);

        public static string LocatePayload()
        {
            var exe = Environment.ProcessPath
                ?? throw new Exception("no exe path");
            var sidecar = exe + ".payload.zip";
            if (File.Exists(sidecar))
                return sidecar;
            // Appended: the last 8 bytes LE are the zip offset.
            using var fs = File.OpenRead(exe);
            if (fs.Length < 8)
                throw new Exception("exe with no payload");
            var tail = new byte[8];
            fs.Seek(-8, SeekOrigin.End);
            fs.ReadExactly(tail, 0, 8);
            long off = BitConverter.ToInt64(tail, 0);
            if (off <= 0 || off >= fs.Length)
                throw new Exception("no payload (package it with make-installer.py)");
            var tmp = Path.Combine(Path.GetTempPath(), "aether-payload.zip");
            using var src = File.OpenRead(exe);
            using var dst = File.Create(tmp);
            src.Seek(off, SeekOrigin.Begin);
            src.CopyTo(dst);
            // Trim the 8 extra footer bytes copied over (the stream length,
            // not FileInfo: the buffer has not been flushed yet).
            dst.Flush();
            dst.SetLength(dst.Length - 8);
            return tmp;
        }

        public static void Install(Options o, IProgress<(long, long)> progress)
        {
            // The language pack is downloaded BEFORE touching the system: if it
            // fails (no network, 404) there is no half-finished install.
            string? lpTmp = null, lpId = null;
            if (o.Lang != "en-US")
                (lpTmp, lpId) = DownloadLangpack(o.Lang);
            var zipPath = LocatePayload();
            // Single root dir? strip it (our portable zip carries aether/...).
            using var zip = ZipFile.OpenRead(zipPath);
            long total = 0;
            foreach (var e in zip.Entries)
                total += e.Length;
            string? root = null;
            bool multi = false;
            foreach (var e in zip.Entries)
            {
                var top = e.FullName.Replace('\\', '/').Split('/')[0];
                if (root is null) root = top;
                else if (root != top) { multi = true; break; }
            }
            long done = 0;
            foreach (var e in zip.Entries)
            {
                var rel = e.FullName.Replace('\\', '/');
                if (!multi)
                {
                    var i = rel.IndexOf('/');
                    rel = i < 0 ? "" : rel[(i + 1)..];
                }
                if (string.IsNullOrEmpty(rel))
                    continue;
                var out_ = Path.Combine(o.Dir, rel.Replace('/', Path.DirectorySeparatorChar));
                if (e.FullName.EndsWith("/"))
                    Directory.CreateDirectory(out_);
                else
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(out_)!);
                    e.ExtractToFile(out_, overwrite: true);
                    done += e.Length;
                    progress.Report((done, total));
                }
            }
            // Local uninstaller: copy under the SAME name (the .NET apphost
            // resolves dll/runtimeconfig from the exe name).
            // Single-file (release): the exe is enough. Normal build
            // (dev): ship the dll + configs alongside if they are there.
            var udir = Path.Combine(o.Dir, "uninstall");
            Directory.CreateDirectory(udir);
            var me = Environment.ProcessPath!;
            File.Copy(me, Path.Combine(udir, Path.GetFileName(me)), true);
            foreach (var f in new[] { "AetherSetup.dll",
                                      "AetherSetup.runtimeconfig.json",
                                      "AetherSetup.deps.json" })
            {
                var src = Path.Combine(AppContext.BaseDirectory, f);
                if (File.Exists(src))
                    File.Copy(src, Path.Combine(udir, f), true);
            }
            // Registro.
            using var k = Hive(o.Scope).CreateSubKey(UnkeyPath);
            k?.SetValue("DisplayName", "Aether Browser");
            k?.SetValue("DisplayVersion", "0.1");
            k?.SetValue("InstallLocation", o.Dir);
            k?.SetValue("DisplayIcon", Path.Combine(o.Dir, "aether.exe"));
            k?.SetValue("UninstallString", $"\"{Path.Combine(udir, Path.GetFileName(Environment.ProcessPath!))}\"");
            // Shortcuts (per-user or all-users hive depending on the scope).
            var desktopFolder = o.Scope == Scope.System
                ? Environment.SpecialFolder.CommonDesktopDirectory
                : Environment.SpecialFolder.Desktop;
            var programsFolder = o.Scope == Scope.System
                ? Environment.SpecialFolder.CommonPrograms
                : Environment.SpecialFolder.Programs;
            var target = Path.Combine(o.Dir, "aether.exe");
            if (o.DesktopIcon)
                CreateLnk(target, Path.Combine(
                    Environment.GetFolderPath(desktopFolder),
                    "Aether Browser.lnk"), "Aether Browser");
            var startm = Path.Combine(
                Environment.GetFolderPath(programsFolder),
                "Aether Browser");
            Directory.CreateDirectory(startm);
            CreateLnk(target, Path.Combine(startm, "Aether Browser.lnk"),
                      "Aether Browser");
            // Langpack re-brandeado a distribution/extensions (precarga).
            if (lpTmp is not null)
            {
                var ext = Path.Combine(o.Dir, "distribution", "extensions");
                Directory.CreateDirectory(ext);
                File.Copy(lpTmp, Path.Combine(ext, lpId + ".xpi"), true);
                try { File.Delete(lpTmp); } catch { }
                // Activate the locale even if it does not match the OS one
                // (intl.locale.requested: comma-separated list).
                var def = Path.Combine(o.Dir, "defaults", "preferences");
                Directory.CreateDirectory(def);
                File.WriteAllText(Path.Combine(def, "aether-lang.js"),
                    "pref(\"intl.locale.requested\", \"" + o.Lang + "\");\n");
            }
            else
            {
                // en-US: nothing left over from another install on top.
                try
                {
                    File.Delete(Path.Combine(o.Dir, "defaults",
                        "preferences", "aether-lang.js"));
                }
                catch { }
            }
            // Spellchecker dictionary (best-effort, does not abort): AMO API,
            // unpatched (word lists) and signed by Mozilla.
            if (o.Lang != "en-US")
            {
                try { InstallDictionary(o.Dir, o.Lang); }
                catch { }
            }
            // Default browser candidacy (ProgIds + Capabilities).
            RegisterAssociations(o.Dir, o.Scope);
        }

        private static void InstallDictionary(string dir, string lang)
        {
            using var http = new System.Net.Http.HttpClient
            {
                Timeout = TimeSpan.FromMinutes(2),
            };
            http.DefaultRequestHeaders.Add("User-Agent", "AetherSetup/0.1");
            string search = http.GetStringAsync(
                "https://services.addons.mozilla.org/api/v4/addons/language-tools/"
                + "?app=firefox&type=dictionary").GetAwaiter().GetResult();
            using var doc = System.Text.Json.JsonDocument.Parse(search);
            string? slug = null, guid = null;
            string? fallSlug = null, fallGuid = null;
            string prefix = lang.Split('-')[0];
            foreach (var r in doc.RootElement.GetProperty("results").EnumerateArray())
            {
                string tl = r.TryGetProperty("target_locale", out var t)
                    ? t.GetString() ?? "" : "";
                if (tl == lang)
                {
                    slug = r.GetProperty("slug").GetString();
                    guid = r.GetProperty("guid").GetString();
                    break;
                }
                if (fallSlug is null && tl.Split('-')[0] == prefix)
                {
                    fallSlug = r.GetProperty("slug").GetString();
                    fallGuid = r.GetProperty("guid").GetString();
                }
            }
            slug ??= fallSlug;
            guid ??= fallGuid;
            if (slug is null || guid is null)
                return; // no dictionary for this language: nothing to do.
            string detail = http.GetStringAsync(
                "https://services.addons.mozilla.org/api/v4/addons/addon/"
                + slug + "/").GetAwaiter().GetResult();
            using var dd = System.Text.Json.JsonDocument.Parse(detail);
            string? url = null;
            foreach (var f in dd.RootElement.GetProperty("current_version")
                         .GetProperty("files").EnumerateArray())
            {
                url = f.GetProperty("url").GetString();
                break;
            }
            if (url is null)
                return;
            byte[] bytes = http.GetByteArrayAsync(url)
                .GetAwaiter().GetResult();
            var ext = Path.Combine(dir, "distribution", "extensions");
            Directory.CreateDirectory(ext);
            File.WriteAllBytes(Path.Combine(ext, guid + ".xpi"), bytes);
        }

        // ---- Langpacks: download from releases.mozilla.org + re-brand ----
        // Base Firefox version (remap on every rebase, see
        // firefox_version.txt). If that point has no xpi/, fall back to X.Y.
        private const string FirefoxBase = "156.0.1";

        private static (string Tmp, string Id) DownloadLangpack(string lang)
        {
            // The XPI file is named after the code (verified against the
            // releases.mozilla.org listing; Langs.cs is the catalogue).
            var file = lang;
            foreach (char c in file)
                if (!(char.IsLetterOrDigit(c) || c == '-'))
                    throw new Exception("Invalid language code: " + lang);
            var id = $"langpack-{file}@firefox.mozilla.org";
            var vers = new[]
            {
                FirefoxBase,
                FirefoxBase[..FirefoxBase.LastIndexOf('.')],
            };
            using var http = new System.Net.Http.HttpClient
            {
                Timeout = TimeSpan.FromMinutes(2),
            };
            Exception? last = null;
            foreach (var v in vers.Distinct())
            {
                var url = "https://releases.mozilla.org/pub/firefox/releases/"
                    + $"{v}/win64/xpi/{file}.xpi";
                try
                {
                    var bytes = http.GetByteArrayAsync(url)
                        .GetAwaiter().GetResult();
                    var tmp = Path.Combine(Path.GetTempPath(), id + ".xpi");
                    File.WriteAllBytes(tmp, bytes);
                    PatchBrand(tmp, file);
                    return (tmp, id);
                }
                catch (Exception ex) { last = ex; }
            }
            throw new Exception("Could not download the language " + lang
                + " (no network?). Install in English or try again. ("
                + last?.Message + ")");
        }

        // The Mozilla langpack stays INTACT (signed): touching one byte
        // breaks the signature and sideload rejects it; AMO also reverts
        // the brand on a major update. The Aether brand lives only in en-US.
        private static void PatchBrand(string xpiPath, string file)
        {
            using var zip = ZipFile.Open(xpiPath, ZipArchiveMode.Update);
            if (zip.GetEntry("manifest.json") is null)
                throw new Exception("The langpack has no manifest.json.");
        }

        // ---- Associations: mirrors browser/installer/windows/nsis ----
        // (shared.nsh SetStartMenuInternet + installer.nsi ProgIds),
        // HKLM only (we install machine-wide as admin). We do not set
        // ourselves as default (Windows forbids it): we only register as
        // a candidate so that Settings and the browser button work.
        private const string Client = "AETHER.EXE";
        private const string ExeName = "aether.exe";

        private static readonly string[] HtmlExts =
            { ".htm", ".html", ".shtml", ".xht", ".xhtml", ".svg", ".webp", ".avif" };

        private static readonly string[] AppTypes =
        {
            ".apng", ".bmp", ".flac", ".gif", ".htm", ".html", ".ico",
            ".jfif", ".jpeg", ".jpg", ".json", ".m4a", ".mp3", ".oga",
            ".ogg", ".ogv", ".opus", ".pdf", ".pjpeg", ".pjp", ".png",
            ".rdf", ".shtml", ".svg", ".webm", ".webp", ".avif", ".xht",
            ".xhtml", ".xml",
        };

        private static void RegisterAssociations(string dir, Scope scope)
        {
            var hive = Hive(scope);
            var exe = Path.Combine(dir, ExeName);
            var open = $"\"{exe}\" -osint -url \"%1\"";
            // ProgIds (Classes).
            ProgId(hive, "AetherHTML", "Aether HTML Document", $"{exe},1", open, false);
            ProgId(hive, "AetherPDF", "Aether PDF Document", $"{exe},1", open, false);
            ProgId(hive, "AetherURL", "Aether URL", $"{exe},1", open, true);
            // Applications\aether.exe (Open with dialog).
            using (var app = hive.CreateSubKey(
                       @"SOFTWARE\Classes\Applications\" + ExeName))
            {
                app?.SetValue("FriendlyAppName", "Aether Browser");
                using var cmd = app?.CreateSubKey(@"shell\open\command");
                cmd?.SetValue("", open);
                using var ico = app?.CreateSubKey("DefaultIcon");
                ico?.SetValue("", $"{exe},1");
                using var sup = app?.CreateSubKey("SupportedTypes");
                if (sup is not null)
                    foreach (var t in AppTypes)
                        sup.SetValue(t, "");
            }
            // Cliente StartMenuInternet + Capabilities.
            var base_ = @"SOFTWARE\Clients\StartMenuInternet\" + Client;
            using (var c = hive.CreateSubKey(base_))
            {
                c?.SetValue("", "Aether Browser");
                using var ico = c?.CreateSubKey("DefaultIcon");
                ico?.SetValue("", $"{exe},0");
                using var oc = c?.CreateSubKey(@"shell\open\command");
                oc?.SetValue("", $"\"{exe}\"");
                using var pr = c?.CreateSubKey(@"shell\properties\command");
                pr?.SetValue("", $"\"{exe}\" -preferences");
                using var sm = c?.CreateSubKey(@"shell\safemode\command");
                sm?.SetValue("", $"\"{exe}\" -safe-mode");
                using var cap = c?.CreateSubKey("Capabilities");
                cap?.SetValue("ApplicationDescription", "Aether Browser");
                cap?.SetValue("ApplicationIcon", $"{exe},0");
                cap?.SetValue("ApplicationName", "Aether");
                using var fa = cap?.CreateSubKey("FileAssociations");
                if (fa is not null)
                {
                    foreach (var e in HtmlExts)
                        fa.SetValue(e, "AetherHTML");
                    fa.SetValue(".pdf", "AetherPDF");
                }
                using var ua = cap?.CreateSubKey("URLAssociations");
                ua?.SetValue("http", "AetherURL");
                ua?.SetValue("https", "AetherURL");
                ua?.SetValue("mailto", "AetherURL");
                using var smi = cap?.CreateSubKey("StartMenu");
                smi?.SetValue("StartMenuInternet", Client);
            }
            using var ra = hive.CreateSubKey(
                @"SOFTWARE\RegisteredApplications");
            ra?.SetValue(Client, base_ + @"\Capabilities");
        }

        private static void ProgId(RegistryKey hive, string id, string display,
                                   string icon, string open, bool protocol)
        {
            using var k = hive.CreateSubKey(
                @"SOFTWARE\Classes\" + id);
            if (k is null)
                return;
            k.SetValue("", display);
            k.SetValue("FriendlyTypeName", display);
            k.SetValue("EditFlags", 2, RegistryValueKind.DWord);
            if (protocol)
                k.SetValue("URL Protocol", "");
            using var ico = k.CreateSubKey("DefaultIcon");
            ico?.SetValue("", icon);
            using var sh = k.CreateSubKey("shell");
            sh?.SetValue("", "open");
            using var cmd = k.CreateSubKey(@"shell\open\command");
            cmd?.SetValue("", open);
            using var dde = k.CreateSubKey(@"shell\open\ddeexec");
            dde?.SetValue("", "");
        }

        private static void UnregisterAssociations(Scope scope)
        {
            var hive = Hive(scope);
            try
            {
                hive.DeleteSubKeyTree(
                    @"SOFTWARE\Clients\StartMenuInternet\" + Client, false);
            }
            catch { }
            foreach (var id in new[] { "AetherHTML", "AetherPDF", "AetherURL" })
            {
                try
                {
                    hive.DeleteSubKeyTree(
                        @"SOFTWARE\Classes\" + id, false);
                }
                catch { }
            }
            try
            {
                hive.DeleteSubKeyTree(
                    @"SOFTWARE\Classes\Applications\" + ExeName, false);
            }
            catch { }
            try
            {
                using var ra = hive.OpenSubKey(
                    @"SOFTWARE\RegisteredApplications", true);
                ra?.DeleteValue(Client, false);
            }
            catch { }
        }

        public static void CreateLnk(string target, string link,
                                      string desc)
        {
            dynamic shell = Activator.CreateInstance(
                Type.GetTypeFromProgID("WScript.Shell")!)!;
            dynamic sc = shell.CreateShortcut(link);
            sc.TargetPath = target;
            sc.Description = desc;
            sc.IconLocation = target;
            sc.Save();
        }

        public record UnOpts(bool Program, bool Shortcuts,
                             bool Registry, bool Profile);

        public static string ProfileDir(bool local) => Path.Combine(
            Environment.GetFolderPath(local
                ? Environment.SpecialFolder.LocalApplicationData
                : Environment.SpecialFolder.ApplicationData),
            "Aether", "Aether");

        public static long DirSize(string p)
        {
            long s = 0;
            try
            {
                foreach (var f in Directory.EnumerateFiles(
                             p, "*", SearchOption.AllDirectories))
                    try { s += new FileInfo(f).Length; } catch { }
            }
            catch { }
            return s;
        }

        public static string FormatMB(long b) => $"{b / 1048576} MB";

        public static void Uninstall(UnOpts o,
                                     IProgress<(long, long)>? progress)
        {
            var me = Environment.ProcessPath!;
            var dir = Path.GetDirectoryName(Path.GetDirectoryName(me))!;
            if (System.Diagnostics.Process.GetProcessesByName("aether").Length > 0)
                throw new Exception("Close Aether Browser before uninstalling.");
            // The scope is inferred from the uninstall entry, requiring it to
            // point at THIS directory (a leftover from another installer must
            // not confuse us).
            var scope = Scope.User;
            try
            {
                using var k = Registry.LocalMachine.OpenSubKey(UnkeyPath);
                if (k?.GetValue("InstallLocation") is string loc &&
                    string.Equals(loc.TrimEnd('\\'), dir.TrimEnd('\\'),
                        StringComparison.OrdinalIgnoreCase))
                    scope = Scope.System;
                else if (k is null)
                {
                    // No entry (partial second pass): fall back to location.
                    var pf = Environment.GetFolderPath(
                        Environment.SpecialFolder.ProgramFiles);
                    var pf86 = Environment.GetFolderPath(
                        Environment.SpecialFolder.ProgramFilesX86);
                    if (dir.StartsWith(pf, StringComparison.OrdinalIgnoreCase)
                        || dir.StartsWith(pf86, StringComparison.OrdinalIgnoreCase))
                        scope = Scope.System;
                }
            }
            catch { }
            if (o.Registry)
                UnregisterAssociations(scope);
            if (o.Shortcuts)
            {
                var startm = Path.Combine(
                    Environment.GetFolderPath(
                        scope == Scope.System
                        ? Environment.SpecialFolder.CommonPrograms
                        : Environment.SpecialFolder.Programs),
                    "Aether Browser");
                try
                {
                    File.Delete(Path.Combine(
                        Environment.GetFolderPath(
                            scope == Scope.System
                            ? Environment.SpecialFolder.CommonDesktopDirectory
                            : Environment.SpecialFolder.Desktop),
                        "Aether Browser.lnk"));
                    Directory.Delete(startm, true);
                }
                catch { }
            }
            // Our own entry is always removed (otherwise it is orphaned).
            try { Hive(scope).DeleteSubKeyTree(UnkeyPath); } catch { }
            var all = new List<string>(
                Directory.EnumerateFileSystemEntries(dir));
            long total = (o.Program ? all.Count : 0) + (o.Profile ? 1 : 0);
            if (total == 0)
                total = 1;
            long done = 0;
            // Profile (optional): roaming + local. Only if the browser is
            // closed (the guard above); anything left open is skipped.
            if (o.Profile)
            {
                foreach (var base_ in new[]
                         {
                             Environment.GetFolderPath(
                                 Environment.SpecialFolder.ApplicationData),
                             Environment.GetFolderPath(
                                 Environment.SpecialFolder.LocalApplicationData),
                         })
                {
                    var prof = Path.Combine(base_, "Aether", "Aether");
                    try
                    {
                        if (Directory.Exists(prof))
                            Directory.Delete(prof, true);
                    }
                    catch { }
                    try
                    {
                        var vendor = Path.Combine(base_, "Aether");
                        if (Directory.Exists(vendor)
                            && Directory.GetFileSystemEntries(vendor).Length == 0)
                            Directory.Delete(vendor);
                    }
                    catch { }
                }
                progress?.Report((++done, total));
            }
            // Temp propios (payloads/descargas a medias).
            try
            {
                foreach (var t in new[] { "aether-payload.zip",
                                          "aether-setup-error.txt" })
                    try
                    {
                        File.Delete(Path.Combine(Path.GetTempPath(), t));
                    }
                    catch { }
            }
            catch { }
            if (o.Program)
                foreach (var f in all)
                {
                    try
                    {
                        if (string.Equals(f, me, StringComparison.OrdinalIgnoreCase))
                            continue;
                        if (Directory.Exists(f)) Directory.Delete(f, true);
                        else File.Delete(f);
                    }
                    catch { }
                    progress?.Report((++done, total));
                }
            // Self-delete on reboot (only if the program was removed;
            // otherwise the exe stays alive to uninstall the rest).
            if (o.Program)
            {
                MoveFileEx(me, null, 0x4);
                MoveFileEx(dir, null, 0x4);
            }
        }

        [System.Runtime.InteropServices.DllImport("kernel32.dll",
            SetLastError = true, CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
        private static extern bool MoveFileEx(string src, string? dst, uint flags);
    }
}

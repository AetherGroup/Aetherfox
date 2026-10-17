using System;
using System.Configuration;
using System.Data;
using System.IO;
using System.Windows;

namespace AetherSetup;

/// <summary>
/// Interaction logic for App.xaml
/// </summary>
public partial class App : System.Windows.Application
{
    // Elevated headless mode: the non-admin installer relaunches itself
    // with --do-install for the "all users" scope. No window, just an exit
    // code + the error file for the parent.
    protected override void OnStartup(StartupEventArgs e)
    {
        var a = e.Args;
        // Copied to <dir>\uninstall\: it is the uninstaller, not the setup.
        // With --uninstall it runs headless; run by hand it asks to confirm.
        var me = Environment.ProcessPath ?? "";
        bool isUninstaller =
            string.Equals(Path.GetFileName(Path.GetDirectoryName(me)),
                          "uninstall", StringComparison.OrdinalIgnoreCase);
        if (Array.IndexOf(a, "--uninstall") >= 0 || isUninstaller)
        {
            if (Array.IndexOf(a, "--uninstall") < 0)
            {
                // Interactivo: dialogo propio (P8).
                var splashU = new SplashWindow();
                splashU.Show();
                splashU.Dispatcher.Invoke(
                    () => { }, System.Windows.Threading.DispatcherPriority.Background);
                MainWindow = new MainWindow(uninstall: true);
                MainWindow.Show();
                splashU.Close();
                base.OnStartup(e);
                return;
            }
            try
            {
                // Headless (scripts): everything out, the profile stays.
                // No windows: exit code + error file.
                Backend.Uninstall(
                    new Backend.UnOpts(true, true, true, false), null);
                Shutdown(0);
            }
            catch (Exception ex)
            {
                try
                {
                    File.WriteAllText(
                        Path.Combine(Path.GetTempPath(),
                                     "aether-setup-error.txt"),
                        ex.Message);
                }
                catch { }
                Shutdown(1);
            }
            return;
        }
        if (Array.IndexOf(a, "--do-install") >= 0)
        {
            string opt(string n)
            {
                var i = Array.IndexOf(a, n);
                return i >= 0 && i + 1 < a.Length ? a[i + 1] : "";
            }
            var opts = new Options(
                opt("--dir"),
                opt("--lang") is string l && l.Length > 0 ? l : "en-US",
                opt("--desktop") != "0",
                opt("--scope") == "system" ? Scope.System : Scope.User);
            try
            {
                Backend.Install(opts,
                    new Progress<(long, long)>(_ => { }));
                Shutdown(0);
            }
            catch (Exception ex)
            {
                try
                {
                    File.WriteAllText(
                        Path.Combine(Path.GetTempPath(),
                                     "aether-setup-error.txt"),
                        ex.Message);
                }
                catch { }
                Shutdown(1);
            }
            return;
        }
        var splash = new SplashWindow();
        splash.Show();
        splash.Dispatcher.Invoke(
            () => { }, System.Windows.Threading.DispatcherPriority.Background);
        MainWindow = new MainWindow();
        MainWindow.Show();
        splash.Close();
        base.OnStartup(e);
    }
}


// touch rebuild

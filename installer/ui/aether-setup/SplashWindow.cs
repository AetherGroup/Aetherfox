using System.Windows;
using System.Windows.Controls;
using WMedia = System.Windows.Media;

namespace AetherSetup;

// Immediate splash window: shown before the MainWindow so that slow
// startups (first run: Defender + single-file self-extraction) do
// not look like a hang. No XAML, to keep the UI untouched.
public sealed class SplashWindow : Window
{
    public SplashWindow()
    {
        Title = "Aether Browser Setup";
        Width = 340;
        Height = 140;
        WindowStyle = WindowStyle.None;
        ResizeMode = ResizeMode.NoResize;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        Topmost = true;
        ShowInTaskbar = false;
        Background = new WMedia.SolidColorBrush(
            WMedia.Color.FromRgb(0x1B, 0x1E, 0x24));

        var stack = new StackPanel
        {
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(24),
        };
        stack.Children.Add(new TextBlock
        {
            Text = "Aether Browser",
            FontSize = 20,
            FontWeight = FontWeights.SemiBold,
            Foreground = WMedia.Brushes.White,
            HorizontalAlignment = System.Windows.HorizontalAlignment.Center,
        });
        stack.Children.Add(new TextBlock
        {
            Text = "Cargando…",
            FontSize = 13,
            Foreground = new WMedia.SolidColorBrush(
                WMedia.Color.FromRgb(0x9A, 0xA0, 0xA8)),
            HorizontalAlignment = System.Windows.HorizontalAlignment.Center,
            Margin = new Thickness(0, 8, 0, 12),
        });
        stack.Children.Add(new System.Windows.Controls.ProgressBar
        {
            IsIndeterminate = true,
            Height = 4,
            BorderThickness = new Thickness(0),
            Background = WMedia.Brushes.Transparent,
        });
        Content = stack;
    }
}

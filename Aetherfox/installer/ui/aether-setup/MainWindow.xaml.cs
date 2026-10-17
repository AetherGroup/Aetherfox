using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace AetherSetup
{
    public partial class MainWindow : Window
    {
        // Animatable proxy for smooth scrolling (VerticalOffset is not animatable).
        private class ScrollProxy : System.Windows.DependencyObject
        {
            public static readonly System.Windows.DependencyProperty
                OffsetProperty =
                    System.Windows.DependencyProperty.Register(
                        "Offset", typeof(double), typeof(ScrollProxy),
                        new System.Windows.PropertyMetadata(
                            0.0, (d, e) => ((ScrollProxy)d).Changed
                                ?.Invoke((double)e.NewValue)));
            public double Offset
            {
                get => (double)GetValue(OffsetProperty);
                set => SetValue(OffsetProperty, value);
            }
            public event Action<double>? Changed;
        }

        private int step = 1;
        private bool busy;
        private Scope scope = Scope.User;
        private bool dirTouched;
        // Installer language (a Langs code). Curated chrome only
        // for en/es/de/fr; the rest = English chrome + terms if present, else en.
        private string instLang = "en-US";

        private string U(string key, string fallback) =>
            I18n.Get(key, instLang) ?? fallback;

        // The original English (XAML), to go back without leftovers when en-US is picked.
        private readonly Dictionary<string, string> En = new();

        private string U(string key) =>
            I18n.Get(key, instLang) ?? En.GetValueOrDefault(key, key);

        private void SnapEn()
        {
            En["dSub"] = DSub.Text;
            En["dTit"] = DTit.Text;
            En["fSub"] = FSub.Text;
            En["fTit"] = FTit.Text;
            En["lSub"] = LSub.Text;
            En["pTit"] = PTit.Text;
            En["ss1"] = SS1.Text;
            En["ss2"] = SS2.Text;
            En["ss3"] = SS3.Text;
            En["ss4"] = SS4.Text;
            En["sSub"] = SSub.Text;
            En["sTit"] = STit.Text;
            En["su1"] = SU1.Text;
            En["su2"] = SU2.Text;
            En["su3"] = SU3.Text;
            En["su4"] = SU4.Text;
            En["tSub"] = TSub.Text;
            En["tTit"] = TTit.Text;
            En["wSet"] = WSet.Text;
            En["wTag"] = WTag.Text;
            En["wVer"] = WVer.Text;
        }

        private void BtnLang_Click(object s, RoutedEventArgs e)
        {
            LangPop.IsOpen = true;
        }

        private void LangPick_Click(object s, RoutedEventArgs e)
        {
            if (s is System.Windows.Controls.Button b
                && b.Tag is string code)
                instLang = code;
            LangPop.IsOpen = false;
            PaintLang();
            LoadTerms();
            ApplyUiLang();
        }

        private void BuildInstMenu()
        {
            LangMenu.Children.Clear();
            foreach (var o in Langs.All)
            {
                // Only languages with translated chrome (en-US = the XAML base).
                // ach/cak/gn/kab/sat/son/trs fall back to EN until translated.
                if (o.Code != "en-US" && I18n.Get("wTag", o.Code) is null)
                    continue;
                var b = new System.Windows.Controls.Button
                {
                    Content = o.Name,
                    Tag = o.Code,
                    Style = (Style)FindResource("LangRow"),
                };
                b.Click += LangPick_Click;
                LangMenu.Children.Add(b);
            }
            if (LangMenu.Children.Count == 0)
            {
                // Maintenance mode (Langs.All is empty): the picker shows why
                // it offers nothing instead of an empty popup. Disabled buttons
                // do not fire LangPick_Click, so instLang stays "en-US".
                LangMenu.Children.Add(new System.Windows.Controls.Button
                {
                    Content = U("lMaint", "Under maintenance"),
                    IsEnabled = false,
                    Style = (Style)FindResource("LangRow"),
                });
            }
        }

        private void PaintLang()
        {
            string name = instLang;
            foreach (var o in Langs.All)
                if (o.Code == instLang)
                {
                    name = o.Name;
                    break;
                }
            LangCode.Text = name;
            ZoomLbl.Text = U("tipZoom", "Zoom");
            PopNote.Text = U("lNote",
                "Spotted a translation mistake? Please tell the Aether project so it can be fixed.");
            foreach (System.Windows.Controls.Button b in LangMenu.Children)
                b.Foreground = new SolidColorBrush(
                    b.Tag is string c && c == instLang
                    ? System.Windows.Media.Color.FromRgb(0x4D, 0xA3, 0xFF)
                    : Colors.White);
        }

        private void ApplyUiLang()
        {
            WTag.Text = U("wTag");
            WTit.Text = U("brand", "Aether Browser");
            WSet.Text = U("wSet");
            Title = "Aether Browser - "
                + U("wSet", "SETUP").Replace(" ", "");
            WVer.Text = U("wVer");
            TTit.Text = U("tTit");
            TSub.Text = U("tSub");
            ChkAccept.Content = U("tAccept", "I accept these terms");
            ChkDecline.Content = U("tDecline", "I do not accept these terms");
            STit.Text = U("sTit");
            SSub.Text = U("sSub");
            RadUser.Content = U("sUser", "Just me (Recommended)");
            RadSystem.Content = U("sSys", "Everyone on this PC");
            SU1.Text = U("su1");
            SU2.Text = U("su2");
            SU3.Text = U("su3");
            SU4.Text = U("su4");
            SS1.Text = U("ss1");
            SS2.Text = U("ss2");
            SS3.Text = U("ss3");
            SS4.Text = U("ss4");
            DTit.Text = U("dTit");
            DSub.Text = U("dSub");
            BtnBrowse.Content = U("dBrowse", "Browse...");
            LblSpace.Text = U("dSpace", "Space required: 370 MB");
            ChkDesktop.Content = U("dDesk", "Create a desktop icon");
            LTit.Text = U("lTit");
            LSub.Text = U("lSub");
            PTit.Text = U("pTit");
            if (!busy)
                LblDetail.Text = U("pPrep", "Preparing...");
            FTit.Text = U("fTit");
            FSub.Text = U("fSub");
            BtnOpen.Content = U("fOpen", "Open Aether Browser");
            UTit.Text = U("uTit", "Remove Aether Browser");
            USub.Text = U("uSub", "Choose what to delete. Nothing outside these items is touched.");
            UBtnRemove.Content = U("uRemove", "Remove");
            UBtnCancel.Content = U("uCancel", "Cancel");
            TipMin.Content = U("tipMin", "Minimize");
            TipZoom.Content = U("tipZoom", "Zoom");
            TipX.Content = U("tipX", "Close");
            BtnBack.Content = U("navBack", "< Back");
            BtnCancel.Content = U("navCancel", "Cancel");
            BuildLangList();
            ShowStep(step);
        }

        // The browser language list (Langs.cs): flag + name.
        private void BuildLangList()
        {
            string keep = LangId();
            LstLang.Items.Clear();
            var white = new SolidColorBrush(
                System.Windows.Media.Color.FromRgb(0xFF, 0xFF, 0xFF));
            var gray = new SolidColorBrush(
                System.Windows.Media.Color.FromRgb(0x8A, 0x9B, 0xB3));
            foreach (var o in Langs.All)
            {
                var row = new System.Windows.Controls.StackPanel
                {
                    Orientation =
                        System.Windows.Controls.Orientation.Vertical,
                    VerticalAlignment = VerticalAlignment.Center,
                    Tag = o,
                };
                var tx = new System.Windows.Controls.StackPanel
                {
                    Margin = new Thickness(0),
                    VerticalAlignment = VerticalAlignment.Center,
                };
                tx.Children.Add(new System.Windows.Controls.TextBlock
                {
                    Text = o.Name,
                    FontSize = 13,
                    FontWeight = FontWeights.SemiBold,
                    Foreground = white,
                });
                tx.Children.Add(new System.Windows.Controls.TextBlock
                {
                    Text = o.Code == "en-US"
                        ? U("lBuilt", "Built in")
                        : U("lDl", "Downloads language pack from Firefox")
                            + " - " + o.Region,
                    FontSize = 12,
                    Foreground = gray,
                });
                row.Children.Add(tx);
                LstLang.Items.Add(row);
            }
            if (LstLang.Items.Count == 0)
            {
                // Maintenance mode (Langs.All is empty): one disabled row saying
                // so, instead of an empty list. It carries no Tag, so LangId()
                // falls back to "en-US" and the install goes in English with no
                // download and no dictionary.
                var tx = new System.Windows.Controls.TextBlock
                {
                    Text = U("lMaint", "Under maintenance")
                        + " — English for now",
                    FontSize = 13,
                    FontWeight = FontWeights.SemiBold,
                    Foreground = gray,
                };
                var row = new System.Windows.Controls.StackPanel
                {
                    Orientation =
                        System.Windows.Controls.Orientation.Vertical,
                    VerticalAlignment = VerticalAlignment.Center,
                    IsEnabled = false,
                };
                row.Children.Add(tx);
                LstLang.Items.Add(row);
            }
            if (LstLang.SelectedIndex < 0 && LstLang.Items.Count > 0)
                LstLang.SelectedIndex = 0;
            for (int i = 0; i < LstLang.Items.Count; i++)
                if (LstLang.Items[i] is System.Windows.Controls.StackPanel r
                    && r.Tag is LangOption lo && lo.Code == keep)
                {
                    LstLang.SelectedIndex = i;
                    break;
                }
        }

        public MainWindow()
        {
            InitializeComponent();
            // Clip everything to the window curve (the red hover must not spill).
            RootBorder.SizeChanged += (_, _) => ApplyClip(16);
            ApplyClip(16);
            // Embedded logo (the setup runs from outside the repo).
            using (var ls = typeof(MainWindow).Assembly
                       .GetManifestResourceStream("setup-hero.png"))
            {
                if (ls is not null)
                {
                    var ms = new MemoryStream();
                    ls.CopyTo(ms);
                    ms.Position = 0;
                    var bmp = new BitmapImage();
                    bmp.BeginInit();
                    bmp.StreamSource = ms;
                    bmp.CacheOption = BitmapCacheOption.OnLoad;
                    bmp.EndInit();
                    bmp.Freeze();
                    Logo.Source = bmp;
                }
                else
                {
                    Logo.Visibility = Visibility.Collapsed;
                    LogoFallback.Visibility = Visibility.Visible;
                }
            }
            // Terms loaded from the repo (same versioned source),
            // rendered as a document (no visible Markdown markers).
            // The H1 is stripped (the page already carries a title).
            // Installer language (en/es/de/fr); falls back to en.
            LoadTerms();
            RtfTerms.Document.FontFamily =
                new System.Windows.Media.FontFamily("./Fonts/#Quicksand");
            RtfTerms.Document.Foreground =
                new System.Windows.Media.SolidColorBrush(
                    System.Windows.Media.Color.FromRgb(0xC7, 0xD0, 0xDC));
            RtfTerms.Document.PagePadding = new Thickness(4);
            // Default scope: this user only (no admin).
            TxtDir.Text = Backend.UserDir;
            TxtDir.TextChanged += (_, _) => { if (step == 3) dirTouched = true; };
            baseW = Width;
            baseH = Height;
            SnapEn();
            BuildInstMenu();
            PaintLang();
            PaintZoom();
            BuildLangList();
            ShowStep(1);
        }

        private void LoadTerms()
        {
            // exacto (terms-pt-BR) > base (terms-pt) > en, incrustados.
            var asm = typeof(MainWindow).Assembly;
            string? pick = null;
            foreach (var c in new[]
                     {
                         $"terms-{instLang}.md",
                         $"terms-{instLang.Split('-')[0]}.md",
                         "terms-en.md",
                     })
            {
                if (asm.GetManifestResourceInfo(c) is not null)
                {
                    pick = c;
                    break;
                }
            }
            string md = "";
            if (pick is not null)
                using (var s = asm.GetManifestResourceStream(pick)!)
                using (var r = new StreamReader(s))
                    md = r.ReadToEnd();
            md = string.Join("\n", md.Split('\n').Where(
                (l, i) => i > 0 || !l.StartsWith("# ")));
            RtfTerms.Document = md.Length > 0
                ? CleanDoc(Markdig.Wpf.Markdown.ToFlowDocument(md))
                : new System.Windows.Documents.FlowDocument(
                    new System.Windows.Documents.Paragraph(
                        new System.Windows.Documents.Run("Terms file not found.")));
        }

        public bool UninstallMode { get; private set; }

        public MainWindow(bool uninstall) : this()
        {
            UninstallMode = uninstall;
            ShowStep(8);
            LoadUnSizes();
        }

        // Real sizes so the choice can be made from data (program + profile).
        private async void LoadUnSizes()
        {
            var me = Environment.ProcessPath!;
            var dir = System.IO.Path.GetDirectoryName(
                System.IO.Path.GetDirectoryName(me))!;
            var sizes = await Task.Run(() =>
            {
                long prog = Backend.DirSize(dir);
                long prof = Backend.DirSize(Backend.ProfileDir(false))
                    + Backend.DirSize(Backend.ProfileDir(true));
                return (prog, prof);
            });
            UProg.Content = $"{U("uProg", "Program files")} ({Backend.FormatMB(sizes.prog)})";
            UProf.Content = $"{U("uProf", "Profile data (bookmarks, history, passwords)")} ({Backend.FormatMB(sizes.prof)})";
            UShort.Content = U("uShort", "Shortcuts (desktop and start menu)");
            UReg.Content = U("uReg", "File associations and default browser entries");
        }

        private async void UBtnRemove_Click(object s, RoutedEventArgs e)
        {
            bool any = UProg.IsChecked == true || UProf.IsChecked == true
                || UShort.IsChecked == true || UReg.IsChecked == true;
            if (!any)
            {
                ULbl.Visibility = Visibility.Visible;
                ULbl.Foreground = new SolidColorBrush(
                    System.Windows.Media.Color.FromRgb(0xE8, 0x54, 0x54));
                ULbl.Text = U("uNone", "Select at least one item to remove.");
                return;
            }
            UProg.IsEnabled = UProf.IsEnabled =
                UShort.IsEnabled = UReg.IsEnabled = false;
            UBtnRemove.IsEnabled = false;
            UTrack.Visibility = Visibility.Visible;
            ULbl.Visibility = Visibility.Visible;
            var opts = new Backend.UnOpts(
                UProg.IsChecked == true, UShort.IsChecked == true,
                UReg.IsChecked == true, UProf.IsChecked == true);
            var progress = new Progress<(long, long)>(t =>
            {
                var (done, total) = t;
                double f = total > 0 ? (double)done / total : 0;
                UFill.Width = Math.Max(0, 400 * Math.Min(1, f));
                ULbl.Text = $"{U("uRemoving", "Removing...")} {(int)(f * 100)}%";
            });
            string? err = await Task.Run(() =>
            {
                try { Backend.Uninstall(opts, progress); return null; }
                catch (Exception ex) { return ex.Message; }
            });
            if (err is null)
            {
                // Final state in the panel: the checks and Remove gone,
                // success message + close button.
                UProg.Visibility = UProf.Visibility =
                    UShort.Visibility = UReg.Visibility =
                    Visibility.Collapsed;
                UBtnRemove.Visibility = Visibility.Collapsed;
                UTrack.Visibility = Visibility.Collapsed;
                ULbl.Visibility = Visibility.Visible;
                ULbl.Foreground = new SolidColorBrush(Colors.White);
                ULbl.FontSize = 14;
                ULbl.Text = U("uDone", "Aether Browser was removed.");
                UBtnCancel.Content = U("navFinish", "Finish");
            }
            else
            {
                ULbl.Visibility = Visibility.Visible;
                ULbl.Foreground = new SolidColorBrush(
                    System.Windows.Media.Color.FromRgb(0xE8, 0x54, 0x54));
                ULbl.Text = err;
                UProg.IsEnabled = UProf.IsEnabled =
                    UShort.IsEnabled = UReg.IsEnabled = true;
                UBtnRemove.IsEnabled = true;
                UTrack.Visibility = Visibility.Collapsed;
                ULbl.Visibility = Visibility.Collapsed;
            }
        }

        private void ApplyClip(double r)        {
            RootBorder.CornerRadius = new CornerRadius(r);
            RootBorder.Clip = new RectangleGeometry(
                new Rect(0, 0, RootBorder.ActualWidth, RootBorder.ActualHeight),
                r, r);
        }

        private void ShowStep(int n)
        {
            step = n;
            P1.Visibility = n == 1 ? Visibility.Visible : Visibility.Collapsed;
            P2.Visibility = n == 2 ? Visibility.Visible : Visibility.Collapsed;
            P3.Visibility = n == 3 ? Visibility.Visible : Visibility.Collapsed;
            P4.Visibility = n == 4 ? Visibility.Visible : Visibility.Collapsed;
            P5.Visibility = n == 5 ? Visibility.Visible : Visibility.Collapsed;
            P6.Visibility = n == 6 ? Visibility.Visible : Visibility.Collapsed;
            P7.Visibility = n == 7 ? Visibility.Visible : Visibility.Collapsed;
            P8.Visibility = n == 8 ? Visibility.Visible : Visibility.Collapsed;
            BtnBack.IsEnabled = (n >= 2 && n <= 4) || n == 7;
            BtnNext.Content = n switch
            {
                1 => U("navInstall", "Install >"),
                2 => U("navAccept", "Accept >"),
                5 => U("navCancel", "Cancel"),
                6 => U("navFinish", "Finish"),
                _ => U("navNext", "Next >"),
            };
            BtnNext.IsEnabled = n != 2 || ChkAccept.IsChecked == true;
            Nav.Visibility = (n == 6 || n == 8)
                ? Visibility.Collapsed : Visibility.Visible;
            // Quick fade-in of the incoming screen.
            if (FindName("P" + n) is System.Windows.Controls.StackPanel p)
            {
                var anim = new System.Windows.Media.Animation.DoubleAnimation(
                    0, 1, TimeSpan.FromMilliseconds(180));
                p.BeginAnimation(OpacityProperty, anim);
            }
        }

        private void TitleBar_MouseLeftButtonDown(object s,
            System.Windows.Input.MouseButtonEventArgs e)
        {
            if (e.LeftButton == System.Windows.Input.MouseButtonState.Pressed)
                DragMove();
        }

        private double baseW = 720;
        private double baseH = 560;
        private double zoomF = 1.0;

        private void BtnZoom_Click(object s, RoutedEventArgs e)
        {
            ZoomPop.IsOpen = true;
        }

        private void ZoomPick_Click(object s, RoutedEventArgs e)
        {
            zoomF = s == Zoom125 ? 1.25 : s == Zoom150 ? 1.5 : 1.0;
            ZoomPop.IsOpen = false;
            PaintZoom();
            ApplyZoom();
        }

        private void PaintZoom()
        {
            var rows = new[] { Zoom100, Zoom125, Zoom150 };
            double[] fs = { 1.0, 1.25, 1.5 };
            for (int i = 0; i < rows.Length; i++)
                rows[i].Foreground = new SolidColorBrush(
                    Math.Abs(fs[i] - zoomF) < 0.01
                    ? System.Windows.Media.Color.FromRgb(0x4D, 0xA3, 0xFF)
                    : Colors.White);
        }

        // The magnifier grows window and content together (the transform only
        // scales the content; the window has to grow with it).
        private void ApplyZoom()
        {
            ScaleAll.ScaleX = zoomF;
            ScaleAll.ScaleY = zoomF;
            double nw = baseW * zoomF, nh = baseH * zoomF;
            Left += (Width - nw) / 2;
            Top += (Height - nh) / 2;
            Width = nw;
            Height = nh;
        }

        private void BtnMin_Click(object s, RoutedEventArgs e)
            => WindowState = WindowState.Minimized;

        private void BtnX_Click(object s, RoutedEventArgs e) => Close();
        private void BtnCancel_Click(object s, RoutedEventArgs e) => Close();

        private void BtnBack_Click(object s, RoutedEventArgs e)
        {
            // Flujo: 1 bienvenida > 7 scope > 2 terminos > 3 dir > 4 idioma.
            if (step == 7) ShowStep(1);
            else if (step == 2) ShowStep(7);
            else if (step == 3) ShowStep(2);
            else if (step == 4) ShowStep(3);
        }

        private void BtnNext_Click(object s, RoutedEventArgs e)
        {
            if (step == 1) ShowStep(7);
            else if (step == 7) ShowStep(2);
            else if (step == 2 && ChkAccept.IsChecked == true) ShowStep(3);
            else if (step == 2 && ChkDecline.IsChecked == true) Close();
            else if (step == 3) ShowStep(4);
            else if (step == 4) StartInstall();
            else if (step == 6) Close();
        }

        private void Scope_Changed(object s, RoutedEventArgs e)
        {
            // Dispara durante InitializeComponent (RadSystem aun null).
            if (RadSystem is null || TxtDir is null)
            {
                scope = Scope.User;
                return;
            }
            scope = RadSystem.IsChecked == true ? Scope.System : Scope.User;
            if (!dirTouched)
                TxtDir.Text = scope == Scope.System
                    ? Backend.SystemDir : Backend.UserDir;
        }

        private void ChkAccept_Changed(object s, RoutedEventArgs e)
        {
            if (step == 2)
            {
                if (ChkAccept.IsChecked == true)
                    ChkDecline.IsChecked = false;
                RefreshStep2();
            }
        }

        private void ChkDecline_Changed(object s, RoutedEventArgs e)
        {
            if (step == 2)
            {
                if (ChkDecline.IsChecked == true)
                    ChkAccept.IsChecked = false;
                RefreshStep2();
            }
        }

        private void RefreshStep2()
        {
            if (ChkDecline.IsChecked == true)
            {
                BtnNext.Content = U("navFinish", "Finish");
                BtnNext.Style = (Style)FindResource("NavDanger");
                BtnNext.IsEnabled = true;
            }
            else
            {
                BtnNext.Content = U("navAccept", "Accept >");
                BtnNext.Style = (Style)FindResource("NavAccent");
                BtnNext.IsEnabled = ChkAccept.IsChecked == true;
            }
        }

        private void BtnOpen_Click(object s, RoutedEventArgs e)
        {
            try
            {
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
                {
                    FileName = Path.Combine(TxtDir.Text, "aether.exe"),
                    UseShellExecute = true,
                });
            }
            catch { }
            Close();
        }

        private void LstLang_PreviewMouseWheel(object s,
            System.Windows.Input.MouseWheelEventArgs e)
        {
            e.Handled = true;
            var sv = FindVisualChild<System.Windows.Controls.ScrollViewer>(
                LstLang);
            if (sv == null)
                return;
            double target = Math.Max(0, Math.Min(sv.ScrollableHeight,
                sv.VerticalOffset - e.Delta * 0.45));
            var proxy = new ScrollProxy { Offset = sv.VerticalOffset };
            proxy.Changed += v => sv.ScrollToVerticalOffset(v);
            var anim = new System.Windows.Media.Animation.DoubleAnimation(
                target, TimeSpan.FromMilliseconds(150))
            { DecelerationRatio = 1.0 };
            var sb = new System.Windows.Media.Animation.Storyboard();
            System.Windows.Media.Animation.Storyboard.SetTarget(
                sb, proxy);
            System.Windows.Media.Animation.Storyboard.SetTargetProperty(
                sb, new PropertyPath(ScrollProxy.OffsetProperty));
            sb.Children.Add(anim);
            sb.Begin();
        }

        private static T? FindVisualChild<T>(System.Windows.DependencyObject o)
            where T : System.Windows.DependencyObject
        {
            for (int i = 0;
                 i < System.Windows.Media.VisualTreeHelper.GetChildrenCount(o);
                 i++)
            {
                var c = System.Windows.Media.VisualTreeHelper.GetChild(o, i);
                if (c is T t)
                    return t;
                var r = FindVisualChild<T>(c);
                if (r != null)
                    return r;
            }
            return null;
        }

        // Clear Markdig default styles (light backgrounds in
        // code, greys): all white over the dark theme.
        private System.Windows.Documents.FlowDocument CleanDoc(
            System.Windows.Documents.FlowDocument doc)
        {
            var white = new System.Windows.Media.SolidColorBrush(
                System.Windows.Media.Colors.White);
            var clear = new System.Windows.Media.SolidColorBrush(
                System.Windows.Media.Colors.Transparent);
            void Inline(System.Windows.Documents.Inline inl)
            {
                inl.Foreground = white;
                inl.Background = clear;
                if (inl is System.Windows.Documents.Span sp)
                    foreach (var c in sp.Inlines)
                        Inline(c);
            }
            void Block(System.Windows.Documents.Block b)
            {
                b.Foreground = white;
                b.LineHeight = 22;
                b.Margin = new Thickness(0, 0, 0, 10);
                b.FontSize = 14;
                switch (b)
                {
                    case System.Windows.Documents.Section s:
                        foreach (var c in s.Blocks)
                            Block(c);
                        break;
                    case System.Windows.Documents.Paragraph p:
                        foreach (var c in p.Inlines)
                            Inline(c);
                        break;
                    case System.Windows.Documents.List l:
                        foreach (System.Windows.Documents.ListItem li
                                 in l.ListItems)
                            foreach (var c in li.Blocks)
                                Block(c);
                        break;
                    case System.Windows.Documents.Table t:
                        foreach (var g in t.RowGroups)
                            foreach (System.Windows.Documents.TableRow r
                                     in g.Rows)
                                foreach (System.Windows.Documents.TableCell c
                                         in r.Cells)
                                    foreach (var b2 in c.Blocks)
                                        Block(b2);
                        break;
                }
            }
            foreach (var b in doc.Blocks)
                Block(b);
            return doc;
        }

        private void BtnBrowse_Click(object s, RoutedEventArgs e)
        {
            var d = new System.Windows.Forms.FolderBrowserDialog();
            if (d.ShowDialog() == System.Windows.Forms.DialogResult.OK)
                TxtDir.Text = d.SelectedPath;
        }

        private async void StartInstall()
        {
            ShowStep(5);
            busy = true;
            var lang = LangId();
            if (lang != "en-US")
                LblDetail.Text = U("pDl", "Downloading language pack...");
            var opts = new Options(
                TxtDir.Text, lang, ChkDesktop.IsChecked == true, scope);
            // System scope without elevation: relaunch elevated and headless.
            if (scope == Scope.System && !Backend.IsElevated())
            {
                await InstallElevated(opts);
                return;
            }
            var progress = new Progress<(long, long)>(t =>
            {
                var (done, total) = t;
                double f = total > 0 ? (double)done / total : 0;
                Fill.Width = Math.Max(0, TrackBar.ActualWidth * Math.Min(1, f));
                LblPct.Text = $"{(int)(f * 100)}%";
                LblDetail.Text = f < 0.25 ? U("ph1", "Copying browser files...")
                    : f < 0.55 ? U("ph2", "Registering Aether Browser...")
                    : f < 0.80 ? U("ph3", "Creating shortcuts...")
                    : U("ph4", "Finishing up...");
            });
            string? err = await Task.Run(() =>
            {
                try { Backend.Install(opts, progress); return null; }
                catch (Exception ex) { return ex.Message; }
            });
            busy = false;
            if (err is null)
                ShowStep(6);
            else
            {
                // TODO: dedicated error screen; for now it goes back.
                System.Windows.MessageBox.Show(err, "Aether Browser Setup",
                    MessageBoxButton.OK, MessageBoxImage.Error);
                ShowStep(3);
            }
        }

        // elevated child (--do-install): the parent waits with the bar running.
        private async Task InstallElevated(Options o)
        {
            LblDetail.Text = U("pElev", "Installing with administrator rights...");
            // No real % (the elevated child does not report): do not show "0%".
            LblPct.Text = "";
            var pulse = new System.Windows.Threading.DispatcherTimer
            {
                Interval = TimeSpan.FromMilliseconds(50),
            };
            // Artificial: it only climbs to 92%; the real end sets the 100%.
            double shown = 0;
            pulse.Tick += (_, _) =>
            {
                shown += (0.92 - shown) * 0.03;
                if (shown > 0.92)
                    shown = 0.92;
                var w = TrackBar.ActualWidth;
                if (w <= 0)
                    return;
                Fill.Width = Math.Max(0, w * shown);
                LblPct.Text = $"{(int)(shown * 100)}%";
            };
            pulse.Start();
            var errFile = Path.Combine(Path.GetTempPath(),
                                       "aether-setup-error.txt");
            try { File.Delete(errFile); } catch { }
            var psi = new ProcessStartInfo
            {
                FileName = Environment.ProcessPath!,
                Arguments = "--do-install --dir \"" + o.Dir + "\""
                    + " --lang " + o.Lang
                    + " --desktop " + (o.DesktopIcon ? "1" : "0")
                    + " --scope system",
                UseShellExecute = true,
                Verb = "runas",
            };
            try
            {
                using var p = Process.Start(psi);
                if (p is null)
                    throw new Exception("Could not request administrator rights.");
                // UAC minimises the frameless windows: restore on the way back.
                WindowState = WindowState.Normal;
                Activate();
                // UAC minimises the frameless windows: restore on the way back.
                await Task.Run(() => p.WaitForExit());
                Dispatcher.Invoke(() =>
                {
                    WindowState = WindowState.Normal;
                    Activate();
                });
                pulse.Stop();
                busy = false;
                if (p.ExitCode == 0)
                {
                    ShowStep(6);
                    return;
                }
                string err = "Installation failed.";
                try { err = File.ReadAllText(errFile); } catch { }
                try { File.Delete(errFile); } catch { }
                System.Windows.MessageBox.Show(err, "Aether Browser Setup",
                    MessageBoxButton.OK, MessageBoxImage.Error);
                ShowStep(7);
            }
            catch (Win32Exception ex) when (ex.NativeErrorCode == 1223)
            {
                // UAC cancelled by the user.
                pulse.Stop();
                busy = false;
                System.Windows.MessageBox.Show(
                    U("uacMsg", "Administrator approval is required to install for everyone. "
                    + "Choose \"Just me\" to install without it."),
                    "Aether Browser Setup",
                    MessageBoxButton.OK, MessageBoxImage.Information);
                ShowStep(7);
            }
            catch (Exception ex)
            {
                pulse.Stop();
                busy = false;
                System.Windows.MessageBox.Show(ex.Message, "Aether Browser Setup",
                    MessageBoxButton.OK, MessageBoxImage.Error);
                ShowStep(7);
            }
        }

        private string LangId()
        {
            if (LstLang.SelectedItem
                    is System.Windows.Controls.StackPanel r
                && r.Tag is LangOption o)
                return o.Code;
            return "en-US";
        }
    }
}

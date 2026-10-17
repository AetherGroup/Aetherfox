<#
Visual mock of the Aether installer (disposable).
- Native WPF, NOT compiled: edit and run to iterate on the design.
- Does nothing real: the steps are navigable, the progress is simulated.
- Once the design is approved it is ported to the real engine (Rust/C++) as a visual spec.

Uso: powershell -ExecutionPolicy Bypass -File installer\mock-installer.ps1
#>
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase
Add-Type -AssemblyName System.Windows.Forms

$BG0 = "#0D2036"; $BG1 = "#060B14"; $ACC = "#4DA3FF"; $ACC2 = "#7DBDFF"
$INK = "#FFFFFF"; $MUT = "#8A9BB3"; $DARK = "#06121F"

$logoPath = Join-Path $PSScriptRoot "..\branding\content\setup-hero.png"
$logoPath = [IO.Path]::GetFullPath($logoPath)
$haveLogo = Test-Path $logoPath

$xaml = @"
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Aetherfox Setup" Height="500" Width="640"
        WindowStartupLocation="CenterScreen" ResizeMode="NoResize"
        WindowStyle="None" AllowsTransparency="True" Background="Transparent"
        Foreground="$INK" FontFamily="Segoe UI">
  <Window.Resources>
    <LinearGradientBrush x:Key="Bg" StartPoint="0,0" EndPoint="1,1">
      <GradientStop Color="#10253F" Offset="0"/>
      <GradientStop Color="#0D2036" Offset="0.35"/>
      <GradientStop Color="#0A1728" Offset="0.7"/>
      <GradientStop Color="#060B14" Offset="1"/>
    </LinearGradientBrush>
    <Style x:Key="Btn" TargetType="Button">
      <Setter Property="Background" Value="$ACC"/>
      <Setter Property="Foreground" Value="$DARK"/>
      <Setter Property="FontWeight" Value="Bold"/>
      <Setter Property="Padding" Value="18,7"/>
      <Setter Property="BorderThickness" Value="0"/>
      <Setter Property="Cursor" Value="Hand"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="Button">
            <Border Background="{TemplateBinding Background}" CornerRadius="8"
                    Padding="{TemplateBinding Padding}">
              <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
            </Border>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="$ACC2"/>
        </Trigger>
      </Style.Triggers>
    </Style>
    <Style x:Key="Ghost" TargetType="Button" BasedOn="{StaticResource Btn}">
      <Setter Property="Background" Value="Transparent"/>
      <Setter Property="Foreground" Value="$MUT"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#1A2A44"/>
          <Setter Property="Foreground" Value="$INK"/>
        </Trigger>
      </Style.Triggers>
    </Style>
    <Style x:Key="ScrollTh" TargetType="Thumb">
      <Setter Property="Background" Value="#23405F"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="Thumb">
            <Border Background="{TemplateBinding Background}" CornerRadius="4" Width="8" Margin="2,0"/>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="$ACC"/>
        </Trigger>
      </Style.Triggers>
    </Style>
    <Style TargetType="ScrollBar">
      <Setter Property="Background" Value="Transparent"/>
      <Setter Property="Width" Value="12"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="ScrollBar">
            <Grid Background="{TemplateBinding Background}">
              <Track Name="PART_Track" IsDirectionReversed="True">
                <Track.Thumb>
                  <Thumb Style="{StaticResource ScrollTh}"/>
                </Track.Thumb>
                <Track.IncreaseRepeatButton>
                  <RepeatButton Command="ScrollBar.PageDownCommand" Opacity="0" Focusable="False"/>
                </Track.IncreaseRepeatButton>
                <Track.DecreaseRepeatButton>
                  <RepeatButton Command="ScrollBar.PageUpCommand" Opacity="0" Focusable="False"/>
                </Track.DecreaseRepeatButton>
              </Track>
            </Grid>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>
  </Window.Resources>

  <Border CornerRadius="16" Background="{StaticResource Bg}"
          BorderBrush="#23405F" BorderThickness="1">
  <Grid>
    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>

    <!-- custom title bar (no native chrome) -->
    <DockPanel Name="TitleBar" Grid.Row="0" Margin="20,12,12,0" Background="Transparent">
      <StackPanel Orientation="Horizontal" DockPanel.Dock="Right">
        <Button Name="BtnMin" Content="_" Style="{StaticResource Ghost}" Width="40" Padding="0,2"/>
        <Button Name="BtnX" Content="X" Style="{StaticResource Ghost}" Width="40" Padding="0,2"/>
      </StackPanel>
      <TextBlock Text="Aetherfox Setup" FontSize="12" Foreground="$MUT" VerticalAlignment="Center"/>
    </DockPanel>

    <!-- P1 welcome -->
    <StackPanel Name="P1" Grid.Row="1" Margin="36,28" VerticalAlignment="Center">
      <Image Name="Logo" Height="64" HorizontalAlignment="Left" Margin="0,0,0,16"/>
      <TextBlock Name="LogoFallback" Text="Aether" FontSize="40" FontWeight="Bold" Margin="0,0,0,8" Visibility="Collapsed"/>
      <TextBlock Text="Aetherfox 0.1" FontSize="26" FontWeight="SemiBold"/>
      <TextBlock Text="Private, fast and honest browsing." FontSize="14" Foreground="$MUT" Margin="0,6,0,4"/>
      <TextBlock Text="Based on Mozilla Firefox 156.0.1." FontSize="12" Foreground="$MUT"/>
    </StackPanel>

    <!-- P2 directory -->
    <StackPanel Name="P2" Grid.Row="1" Margin="36,28" VerticalAlignment="Center" Visibility="Collapsed">
      <TextBlock Text="Install location" FontSize="22" FontWeight="SemiBold"/>
      <TextBlock Text="Choose where to install Aetherfox." FontSize="13" Foreground="$MUT" Margin="0,6,0,16"/>
      <DockPanel>
        <Button Name="BtnBrowse" Content="Browse..." Style="{StaticResource Ghost}" DockPanel.Dock="Right" Margin="8,0,0,0"/>
        <TextBox Name="TxtDir" Text="C:\Program Files\Aetherfox" Padding="8,6"
                 Background="#0A1526" Foreground="$INK" BorderBrush="#23405F"/>
      </DockPanel>
      <TextBlock Name="LblSpace" Text="Space required: 370 MB  •  Available: 1.2 TB" FontSize="12" Foreground="$MUT" Margin="0,12,0,16"/>
      <CheckBox Name="ChkDesktop" Content="Create a desktop icon" IsChecked="True" Foreground="$INK" FontSize="13" Margin="0,0,0,4"/>
    </StackPanel>

    <!-- P3 language -->
    <StackPanel Name="P3" Grid.Row="1" Margin="36,28" VerticalAlignment="Center" Visibility="Collapsed">
      <TextBlock Text="Language" FontSize="22" FontWeight="SemiBold"/>
      <TextBlock Text="Aether speaks English out of the box. Other languages download their language pack from Firefox on first run." FontSize="13" Foreground="$MUT" Margin="0,6,0,16" TextWrapping="Wrap"/>
      <ListBox Name="LstLang" SelectedIndex="0" Background="Transparent" BorderThickness="0" MaxHeight="188">
        <ListBox.ItemContainerStyle>
          <Style TargetType="ListBoxItem">
            <Setter Property="Background" Value="#0A1526"/>
            <Setter Property="Foreground" Value="$INK"/>
            <Setter Property="Padding" Value="10,7"/>
            <Setter Property="Margin" Value="0,0,0,8"/>
            <Setter Property="BorderBrush" Value="#23405F"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template">
              <Setter.Value>
                <ControlTemplate TargetType="ListBoxItem">
                  <Border Background="{TemplateBinding Background}" BorderBrush="{TemplateBinding BorderBrush}" BorderThickness="{TemplateBinding BorderThickness}" CornerRadius="10" Padding="{TemplateBinding Padding}">
                    <ContentPresenter/>
                  </Border>
                </ControlTemplate>
              </Setter.Value>
            </Setter>
            <Style.Triggers>
              <Trigger Property="IsMouseOver" Value="True">
                <Setter Property="BorderBrush" Value="$ACC2"/>
              </Trigger>
              <Trigger Property="IsSelected" Value="True">
                <Setter Property="Background" Value="#14304D"/>
                <Setter Property="BorderBrush" Value="$ACC"/>
              </Trigger>
            </Style.Triggers>
          </Style>
        </ListBox.ItemContainerStyle>
        <ListBoxItem>
          <StackPanel>
            <TextBlock Text="English (US)" FontSize="13" FontWeight="SemiBold"/>
            <TextBlock Text="Built in" FontSize="12" Foreground="$MUT"/>
          </StackPanel>
        </ListBoxItem>
        <ListBoxItem>
          <StackPanel>
            <TextBlock Text="Español (ES)" FontSize="13" FontWeight="SemiBold"/>
            <TextBlock Text="Downloads language pack from Firefox" FontSize="12" Foreground="$MUT"/>
          </StackPanel>
        </ListBoxItem>
        <ListBoxItem>
          <StackPanel>
            <TextBlock Text="Deutsch" FontSize="13" FontWeight="SemiBold"/>
            <TextBlock Text="Downloads language pack from Firefox" FontSize="12" Foreground="$MUT"/>
          </StackPanel>
        </ListBoxItem>
        <ListBoxItem>
          <StackPanel>
            <TextBlock Text="Français" FontSize="13" FontWeight="SemiBold"/>
            <TextBlock Text="Downloads language pack from Firefox" FontSize="12" Foreground="$MUT"/>
          </StackPanel>
        </ListBoxItem>
      </ListBox>
    </StackPanel>

    <!-- P4 progress -->
    <StackPanel Name="P4" Grid.Row="1" Margin="36,28" VerticalAlignment="Center" Visibility="Collapsed">
      <TextBlock Text="Installing..." FontSize="22" FontWeight="SemiBold"/>
      <TextBlock Name="LblDetail" Text="Preparing..." FontSize="13" Foreground="$MUT" Margin="0,6,0,16"/>
      <Border Height="10" CornerRadius="5" Background="#0A1526" Margin="0,0,0,0">
        <Rectangle Name="Fill" Fill="$ACC" RadiusX="5" RadiusY="5"
                   HorizontalAlignment="Left" Width="0"/>
      </Border>
      <TextBlock Name="LblPct" Text="0%" FontSize="12" Foreground="$MUT" Margin="0,8,0,0"/>
    </StackPanel>

    <!-- P5 finish -->
    <StackPanel Name="P5" Grid.Row="1" Margin="36,28" VerticalAlignment="Center" Visibility="Collapsed">
      <TextBlock Text="Done" FontSize="26" FontWeight="SemiBold"/>
      <TextBlock Text="Aetherfox 0.1 is installed." FontSize="14" Foreground="$MUT" Margin="0,6,0,16"/>
      <Button Name="BtnOpen" Content="Open Aetherfox" Style="{StaticResource Btn}" HorizontalAlignment="Left" Padding="22,8"/>
    </StackPanel>

    <!-- nav -->
    <DockPanel Grid.Row="2" Margin="36,0,36,24">
      <Button Name="BtnCancel" Content="Cancel" Style="{StaticResource Ghost}" DockPanel.Dock="Left"/>
      <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
        <Button Name="BtnBack" Content="&lt; Back" Style="{StaticResource Ghost}" Margin="0,0,8,0"/>
        <Button Name="BtnNext" Content="Install &gt;" Style="{StaticResource Btn}"/>
      </StackPanel>
    </DockPanel>
  </Grid>
  </Border>
</Window>
"@

$reader = [XML.XMLReader]::Create([IO.StringReader]$xaml)
$w = [Windows.Markup.XamlReader]::Load($reader)
$get = { param($n) $w.FindName($n) }

if ($haveLogo) {
  $bmp = New-Object Windows.Media.Imaging.BitmapImage
  $bmp.BeginInit()
  $bmp.UriSource = [Uri]$logoPath
  $bmp.EndInit()
  (& $get "Logo").Source = $bmp
} else {
  (& $get "Logo").Visibility = "Collapsed"
  (& $get "LogoFallback").Visibility = "Visible"
}

$script:step = 1
$pages = @((& $get "P1"), (& $get "P2"), (& $get "P3"), (& $get "P4"), (& $get "P5"))
$nextBtn = & $get "BtnNext"
$backBtn = & $get "BtnBack"
$cancelBtn = & $get "BtnCancel"

$script:pct = 0
$timer = New-Object Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromMilliseconds(90)
$timer.Add_Tick({
  $script:pct = [Math]::Min(100, $script:pct + 1.7)
  $v = [int]$script:pct
  (& $get "Fill").Width = 540 * $script:pct / 100
  (& $get "LblPct").Text = "$v%"
  $d = (& $get "LblDetail")
  if ($v -lt 25) { $d.Text = "Copying browser files..." }
  elseif ($v -lt 55) { $d.Text = "Registering Aetherfox..." }
  elseif ($v -lt 80) { $d.Text = "Creating shortcuts..." }
  else { $d.Text = "Finishing up..." }
  if ($script:pct -ge 100) { $timer.Stop(); Show-Step 5 }
})

function Show-Step($n) {
  $script:step = $n
  for ($i = 0; $i -lt 5; $i++) {
    $pages[$i].Visibility = if ($i -eq ($n - 1)) { "Visible" } else { "Collapsed" }
  }
  $backBtn.IsEnabled = ($n -ge 2 -and $n -le 4)
  $nextBtn.Content = switch ($n) { 1 { "Install >" } 4 { "Cancel" } 5 { "Finish" } default { "Next >" } }
  $cancelBtn.Visibility = if ($n -eq 5) { "Collapsed" } else { "Visible" }
  if ($n -eq 4) { $script:pct = 0; (& $get "Fill").Width = 0; $timer.Start() } else { $timer.Stop() }
}

(& $get "TitleBar").Add_MouseLeftButtonDown({ $w.DragMove() })
(& $get "BtnMin").Add_Click({ $w.WindowState = "Minimized" })
(& $get "BtnX").Add_Click({ $timer.Stop(); $w.Close() })
(& $get "BtnOpen").Add_Click({ $timer.Stop(); $w.Close() })
$backBtn.Add_Click({
  if ($script:step -eq 2) { Show-Step 1 }
  elseif ($script:step -eq 3) { Show-Step 2 }
  elseif ($script:step -eq 4) { $timer.Stop(); Show-Step 3 }
})
$nextBtn.Add_Click({
  if ($script:step -eq 1) { Show-Step 2 }
  elseif ($script:step -eq 2) { Show-Step 3 }
  elseif ($script:step -eq 3) { Show-Step 4 }
  elseif ($script:step -eq 4) { $timer.Stop(); Show-Step 3 }
  elseif ($script:step -eq 5) { $w.Close() }
})
$cancelBtn.Add_Click({ $timer.Stop(); $w.Close() })
(& $get "BtnBrowse").Add_Click({
  $d = New-Object Windows.Forms.FolderBrowserDialog
  if ($d.ShowDialog() -eq "OK") { (& $get "TxtDir").Text = $d.SelectedPath }
})

Show-Step 1
[void]$w.ShowDialog()

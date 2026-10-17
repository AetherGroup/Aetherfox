namespace AetherSetup
{
    // Languages the installer offers for the browser.
    // Policy: only locales whose brand we maintain ship here, and right now
    // that is none. en-US is built in and needs no entry; Spanish is next once
    // its brand files exist, and the rest wait for the translation site. Every
    // removed entry is one `git show` away in the history of this file.
    // Until entries come back, both language sections in the UI show as
    // "under maintenance" (see BuildInstMenu / BuildLangList) instead of
    // offering downloads we cannot brand.
    //
    // Code == the XPI file name on releases.mozilla.org (verified against
    // 156.0.1/win64/xpi/). C1..C3: flag-suggestive stripes (Vertical =
    // vertical tricolour). At 26x17 only the colour gesture is
    // distinguishable.
    public record LangOption(string Code, string Name, string Region,
                             string C1, string C2, string C3, bool Vertical);

    public static class Langs
    {
        public static readonly LangOption[] All = new LangOption[]
        {
        };
    }
}

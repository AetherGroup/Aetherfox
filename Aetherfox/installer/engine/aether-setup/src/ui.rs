//! Installer UI (port of the WPF mock). Chrome-less window,
//! 5 screens, worker thread with real progress from the backend.
use std::sync::mpsc;

use eframe::egui;

use crate::install;

const MUT: egui::Color32 = egui::Color32::from_rgb(0x8a, 0x9b, 0xb3);
const ACC: egui::Color32 = egui::Color32::from_rgb(0x4d, 0xa3, 0xff);
const ACC_DK: egui::Color32 = egui::Color32::from_rgb(0x06, 0x12, 0x1f);
const CARD: egui::Color32 = egui::Color32::from_rgb(0x0d, 0x20, 0x36);
const TRACK: egui::Color32 = egui::Color32::from_rgb(0x0a, 0x15, 0x26);
const LINE: egui::Color32 = egui::Color32::from_rgb(0x23, 0x40, 0x5f);
const SELBG: egui::Color32 = egui::Color32::from_rgb(0x14, 0x30, 0x4d);

const LANGS: &[(&str, &str, bool)] = &[
    ("en-US", "English (US)", true),
    ("es-ES", "Español (ES)", false),
    ("de", "Deutsch", false),
    ("fr", "Français", false),
];

#[derive(PartialEq, Clone, Copy)]
enum Screen {
    Welcome,
    Directory,
    Language,
    Progress,
    Finish,
}

enum Msg {
    Progress(u64, u64),
    Done(Result<(), String>),
}

pub struct App {
    screen: Screen,
    dir: String,
    lang: usize,
    desktop_icon: bool,
    frac: f32,
    detail: String,
    error: String,
    rx: Option<mpsc::Receiver<Msg>>,
}

impl App {
    fn new(cc: &eframe::CreationContext<'_>) -> Self {
        let mut visuals = egui::Visuals::dark();
        visuals.window_fill = egui::Color32::TRANSPARENT;
        visuals.panel_fill = egui::Color32::TRANSPARENT;
        cc.egui_ctx.set_visuals(visuals);
        Self {
            screen: Screen::Welcome,
            dir: install::DEFAULT_DIR.to_string(),
            lang: 0,
            desktop_icon: true,
            frac: 0.0,
            detail: "Preparing...".into(),
            error: String::new(),
            rx: None,
        }
    }

    fn accent_btn(ui: &mut egui::Ui, text: &str) -> egui::Response {
        ui.add_sized(
            [150.0, 34.0],
            egui::Button::new(egui::RichText::new(text).strong().color(ACC_DK))
                .fill(ACC)
                .corner_radius(8.0),
        )
    }

    fn ghost_btn(ui: &mut egui::Ui, text: &str) -> egui::Response {
        ui.add_sized(
            [110.0, 34.0],
            egui::Button::new(egui::RichText::new(text).color(MUT))
                .fill(egui::Color32::TRANSPARENT)
                .corner_radius(8.0),
        )
    }

    fn start_install(&mut self) {
        let opts = install::Options {
            dir: self.dir.clone(),
            lang: LANGS[self.lang].0.to_string(),
            desktop_icon: self.desktop_icon,
        };
        let (tx, rx) = mpsc::channel();
        self.rx = Some(rx);
        self.frac = 0.0;
        self.error.clear();
        std::thread::spawn(move || {
            let r = install::run(&opts, &|done, total| {
                let _ = tx.send(Msg::Progress(done, total));
            });
            let _ = tx.send(Msg::Done(r));
        });
        self.screen = Screen::Progress;
    }

    fn poll(&mut self, ctx: &egui::Context) {
        let rx = match &self.rx {
            Some(r) => r,
            None => return,
        };
        let mut busy = false;
        let mut done_msg: Option<Result<(), String>> = None;
        while let Ok(m) = rx.try_recv() {
            match m {
                Msg::Progress(done, total) => {
                    if total > 0 {
                        self.frac = (done as f32 / total as f32).min(1.0);
                    }
                    let v = (self.frac * 100.0) as u32;
                    self.detail = if v < 25 {
                        "Copying browser files..."
                    } else if v < 55 {
                        "Registering Aether Browser..."
                    } else if v < 80 {
                        "Creating shortcuts..."
                    } else {
                        "Finishing up..."
                    }
                    .to_string();
                    busy = true;
                }
                Msg::Done(r) => {
                    done_msg = Some(r);
                }
            }
        }
        if let Some(r) = done_msg {
            self.rx = None;
            match r {
                Ok(()) => self.screen = Screen::Finish,
                Err(e) => {
                    self.error = e;
                    self.screen = Screen::Directory;
                }
            }
        } else if self.rx.is_some() {
            busy = true;
        }
        if busy {
            ctx.request_repaint();
        }
    }
}

impl eframe::App for App {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        self.poll(&ctx);
        egui::CentralPanel::default()
            .frame(egui::Frame::NONE.fill(CARD).corner_radius(16.0))
            .show(ui, |ui: &mut egui::Ui| {
                // Drag only from the title bar.
                let titleresp = ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("Aether Browser Setup")
                            .size(12.0)
                            .color(MUT),
                    );
                    ui.with_layout(
                        egui::Layout::right_to_left(egui::Align::Center),
                        |ui| {
                            if ui.small_button("X").clicked() {
                                ctx.send_viewport_cmd(
                                    egui::ViewportCommand::Close,
                                );
                            }
                            if ui.small_button("_").clicked() {
                                ctx.send_viewport_cmd(
                                    egui::ViewportCommand::Minimized(true),
                                );
                            }
                        },
                    );
                });
                if ui.interact(titleresp.response.rect,
                               ui.id().with("drag"),
                               egui::Sense::drag()).dragged()
                {
                    ctx.send_viewport_cmd(egui::ViewportCommand::StartDrag);
                }
                ui.add_space(8.0);
                match self.screen {
                    Screen::Welcome => self.show_welcome(ui),
                    Screen::Directory => self.show_directory(ui),
                    Screen::Language => self.show_language(ui),
                    Screen::Progress => self.show_progress(ui),
                    Screen::Finish => self.show_finish(ui, &ctx),
                }
            });
    }
}

impl App {
    fn show_welcome(&mut self, ui: &mut egui::Ui) {
        ui.heading(
            egui::RichText::new("Aether Browser 0.1").size(26.0).strong(),
        );
        ui.label(
            egui::RichText::new("Private, fast and honest browsing.")
                .size(14.0)
                .color(MUT),
        );
        ui.label(
            egui::RichText::new("Based on Mozilla Firefox 156.0.1.")
                .size(12.0)
                .color(MUT),
        );
        ui.add_space(24.0);
        ui.horizontal(|ui| {
            ui.with_layout(
                egui::Layout::right_to_left(egui::Align::Center),
                |ui| {
                    if Self::accent_btn(ui, "Install >").clicked() {
                        self.screen = Screen::Directory;
                    }
                },
            );
        });
    }

    fn show_directory(&mut self, ui: &mut egui::Ui) {
        ui.heading(
            egui::RichText::new("Install location").size(22.0).strong(),
        );
        ui.label(
            egui::RichText::new("Choose where to install Aether Browser.")
                .color(MUT),
        );
        ui.add_space(12.0);
        ui.add_sized([430.0, 30.0],
                     egui::TextEdit::singleline(&mut self.dir));
        ui.add_space(8.0);
        ui.checkbox(&mut self.desktop_icon, "Create a desktop icon");
        if !self.error.is_empty() {
            ui.colored_label(
                egui::Color32::from_rgb(0xff, 0x7a, 0x7a),
                &self.error,
            );
        }
        ui.add_space(16.0);
        ui.horizontal(|ui| {
            if Self::ghost_btn(ui, "< Back").clicked() {
                self.screen = Screen::Welcome;
            }
            ui.with_layout(
                egui::Layout::right_to_left(egui::Align::Center),
                |ui| {
                    if Self::accent_btn(ui, "Next >").clicked() {
                        self.screen = Screen::Language;
                    }
                },
            );
        });
    }

    fn show_language(&mut self, ui: &mut egui::Ui) {
        ui.heading(egui::RichText::new("Language").size(22.0).strong());
        ui.label(
            egui::RichText::new(
                "Aether speaks English out of the box. Other languages \
                 download their language pack from Firefox on first run.",
            )
            .color(MUT),
        );
        ui.add_space(12.0);
        egui::ScrollArea::vertical().max_height(220.0).show(ui, |ui| {
            for (i, (_id, name, builtin)) in LANGS.iter().enumerate() {
                let note = if *builtin {
                    "Built in"
                } else {
                    "Downloads language pack from Firefox"
                };
                let sel = self.lang == i;
                let inner = egui::Frame::NONE
                    .fill(if sel { SELBG } else { TRACK })
                    .stroke(egui::Stroke::new(
                        1.0,
                        if sel { ACC } else { LINE },
                    ))
                    .corner_radius(10.0)
                    .inner_margin(egui::Margin::symmetric(14, 9))
                    .show(ui, |ui| {
                        ui.vertical(|ui| {
                            ui.label(
                                egui::RichText::new(*name)
                                    .size(13.0)
                                    .strong(),
                            );
                            ui.label(
                                egui::RichText::new(note)
                                    .size(11.0)
                                    .color(MUT),
                            );
                        });
                    });
                if inner
                    .response
                    .interact(egui::Sense::click())
                    .clicked()
                {
                    self.lang = i;
                }
            }
        });
        ui.add_space(12.0);
        ui.horizontal(|ui| {
            if Self::ghost_btn(ui, "< Back").clicked() {
                self.screen = Screen::Directory;
            }
            ui.with_layout(
                egui::Layout::right_to_left(egui::Align::Center),
                |ui| {
                    if Self::accent_btn(ui, "Next >").clicked() {
                        self.start_install();
                    }
                },
            );
        });
    }

    fn show_progress(&mut self, ui: &mut egui::Ui) {
        ui.heading(
            egui::RichText::new("Installing...").size(22.0).strong(),
        );
        ui.label(egui::RichText::new(&self.detail).color(MUT));
        ui.add_space(12.0);
        let w = ui.available_width().min(540.0);
        let (rect, _) =
            ui.allocate_exact_size(egui::vec2(w, 10.0), egui::Sense::hover());
        let p = ui.painter();
        p.rect_filled(rect, 5.0, TRACK);
        let fw = w * self.frac;
        if fw > 0.5 {
            p.rect_filled(
                egui::Rect::from_min_size(rect.min, egui::vec2(fw, 10.0)),
                5.0,
                ACC,
            );
        }
        ui.add_space(6.0);
        ui.label(
            egui::RichText::new(format!("{}%", (self.frac * 100.0) as u32))
                .color(MUT),
        );
        ui.add_space(12.0);
        ui.horizontal(|ui| {
            if Self::ghost_btn(ui, "Cancel").clicked() {
                self.rx = None;
                self.screen = Screen::Language;
            }
        });
    }

    fn show_finish(&mut self, ui: &mut egui::Ui, ctx: &egui::Context) {
        ui.heading(egui::RichText::new("Done").size(26.0).strong());
        ui.label(
            egui::RichText::new("Aether Browser 0.1 is installed.")
                .size(14.0)
                .color(MUT),
        );
        ui.add_space(16.0);
        ui.horizontal(|ui| {
            if Self::accent_btn(ui, "Open Aether Browser").clicked() {
                install::open_browser(&self.dir);
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
            if Self::ghost_btn(ui, "Close").clicked() {
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
        });
    }
}

pub fn run() {
    let opts = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([640.0, 500.0])
            .with_decorations(false)
            .with_transparent(true)
            .with_resizable(false),
        ..Default::default()
    };
    let _ = eframe::run_native(
        "Aether Browser Setup",
        opts,
        Box::new(|cc| Ok(Box::new(App::new(cc)))),
    );
}

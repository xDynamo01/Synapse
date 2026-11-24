//! Native adaptation of Ethan Rogers' JARVIS orb.ts.
//! Source, commit and personal/non-commercial license: ../third_party/jarvis/.
use crate::AppShell;
use slint::{Image, SharedPixelBuffer};
use std::{
    cell::RefCell,
    f32::consts::{PI, TAU},
    time::Instant,
};
use tiny_skia::{BlendMode, Color, Paint, PathBuilder, Pixmap, Stroke, Transform};

const SIZE: u32 = 900;
const COUNT: usize = 2000;
type Point = [f32; 3];

struct Particle {
    position: Point,
    velocity: Point,
    phase: f32,
}

struct Electron {
    start: Point,
    end: Point,
    progress: f32,
    speed: f32,
}

struct Orb {
    particles: Vec<Particle>,
    electrons: Vec<Electron>,
    seed: u64,
    time: f32,
    radius: f32,
    speed: f32,
    brightness: f32,
    point_size: f32,
    line_amount: f32,
    rotation: Point,
    depth: f32,
    depth_velocity: f32,
    transition: f32,
    state: String,
    color: Point,
    last_electron: f32,
}

fn random(seed: &mut u64) -> f32 {
    *seed ^= *seed << 13;
    *seed ^= *seed >> 7;
    *seed ^= *seed << 17;
    (*seed >> 40) as f32 / (1u32 << 24) as f32
}

fn approach(value: &mut f32, target: f32, amount: f32) {
    *value += (target - *value) * amount;
}

impl Orb {
    fn new() -> Self {
        let mut seed = 0x62b9c87d23u64;
        let particles = (0..COUNT)
            .map(|_| {
                let theta = random(&mut seed) * TAU;
                let phi = (2.0 * random(&mut seed) - 1.0).acos();
                let radius = random(&mut seed).sqrt() * 25.0;
                Particle {
                    position: [
                        radius * phi.sin() * theta.cos(),
                        radius * phi.sin() * theta.sin(),
                        radius * phi.cos(),
                    ],
                    velocity: [0.0; 3],
                    phase: random(&mut seed) * 1000.0,
                }
            })
            .collect();
        Self {
            particles,
            electrons: Vec::new(),
            seed,
            time: 0.0,
            radius: 25.0,
            speed: 0.3,
            brightness: 0.6,
            point_size: 0.4,
            line_amount: 0.0,
            rotation: [0.0; 3],
            depth: 0.0,
            depth_velocity: 0.0,
            transition: 0.0,
            state: "idle".into(),
            color: [76.0, 168.0, 232.0],
            last_electron: 0.0,
        }
    }

    fn step(&mut self, state: &str, audio: f32) {
        let t = self.time;
        self.time += 1.0 / 60.0;
        let (radius, speed, bright, size, lines, color) = match state {
            "listening" => (22.0, 0.3, 0.65, 0.4, 0.4, [76.0, 168.0, 232.0]),
            "processing" | "thinking" => (16.0, 0.5, 0.7, 0.3, 1.0, [110.0, 196.0, 255.0]),
            "speaking" => (18.0, 0.2, 0.7, 0.4, 0.8, [90.0, 184.0, 240.0]),
            _ => (28.0, 0.2, 0.5, 0.35, 0.15, [76.0, 168.0, 232.0]),
        };
        approach(&mut self.radius, radius, 0.02);
        approach(&mut self.speed, speed, 0.02);
        approach(&mut self.brightness, bright, 0.02);
        approach(&mut self.point_size, size, 0.02);
        approach(&mut self.line_amount, lines, 0.02);
        for (channel, target) in self.color.iter_mut().zip(color) {
            approach(channel, target, 0.015);
        }
        if state != self.state {
            self.transition = 1.0;
            self.state = state.into();
        }
        self.transition *= 0.985;
        if self.transition > 0.05 {
            self.rotation[0] += self.transition * 0.012 * (t * 1.7).sin();
            self.rotation[1] += self.transition * 0.015;
            self.rotation[2] += self.transition * 0.008 * (t * 1.3).cos();
        }
        let bass = if state == "speaking" {
            audio.clamp(0.0, 1.0)
        } else {
            0.0
        };
        let z_target = match state {
            "processing" | "thinking" => (t * 0.3).sin() * 15.0 + (t * 0.9).sin() * 6.0,
            "speaking" => (t * 0.15).sin() * 6.0 - bass * 10.0,
            _ => (t * 0.12).sin() * 8.0,
        };
        self.depth_velocity += (z_target - self.depth) * 0.008;
        self.depth_velocity *= 0.94;
        self.depth += self.depth_velocity;
        for particle in &mut self.particles {
            let [x, y, z] = particle.position;
            let phase = particle.phase;
            let drift = [
                (t * 0.05 + phase).sin() * 0.001
                    + (t * 0.02 + phase * 2.1 + y * 0.1).sin() * 0.0008,
                (t * 0.06 + phase * 1.3).cos() * 0.001
                    + (t * 0.025 + phase * 1.7 + z * 0.1).cos() * 0.0008,
                (t * 0.055 + phase * 0.7).sin() * 0.001
                    + (t * 0.022 + phase * 0.9 + x * 0.1).sin() * 0.0008,
            ];
            let distance = (x * x + y * y + z * z).sqrt().max(0.01);
            let pull = (distance - self.radius).max(0.0) * 0.002 + 0.0003;
            for (axis, drift) in drift.into_iter().enumerate() {
                let normal = particle.position[axis] / distance;
                particle.velocity[axis] += drift * self.speed - normal * pull;
                if bass > 0.05 {
                    particle.velocity[axis] += normal * bass * 0.02;
                }
                if bass > 0.1 && axis < 2 {
                    particle.velocity[axis] += normal * bass * 0.012 * (t * 8.0 + phase).sin();
                }
                particle.velocity[axis] *= 0.992;
                particle.position[axis] += particle.velocity[axis];
            }
        }
        for electron in &mut self.electrons {
            electron.progress += electron.speed;
        }
        self.electrons.retain(|electron| electron.progress < 1.0);
    }

    fn project(&self, point: Point) -> (f32, f32, f32) {
        let [mut x, mut y, mut z] = point;
        let (sx, cx) = self.rotation[0].sin_cos();
        let (sy, cy) = self.rotation[1].sin_cos();
        let (sz, cz) = self.rotation[2].sin_cos();
        (y, z) = (y * cx - z * sx, y * sx + z * cx);
        (x, z) = (x * cy + z * sy, -x * sy + z * cy);
        (x, y) = (x * cz - y * sz, x * sz + y * cz);
        z += self.depth;
        // Perspective camera at z=80, 45-degree FOV, with slow lateral drift.
        let camera_x = (self.time * 0.02).sin() * 5.0;
        let camera_y = (self.time * 0.03).cos() * 3.0;
        x -= camera_x * z / 80.0;
        y -= camera_y * z / 80.0;
        let perspective = SIZE as f32 / (2.0 * (PI / 8.0).tan() * (80.0 - z).max(3.0));
        (
            SIZE as f32 * 0.5 + x * perspective,
            SIZE as f32 * 0.5 - y * perspective,
            perspective,
        )
    }

    fn render(&mut self, audio: f32) -> Pixmap {
        let mut canvas = Pixmap::new(SIZE, SIZE).expect("Presence canvas");
        canvas.fill(Color::from_rgba8(5, 5, 8, 255));
        let projected: Vec<_> = self
            .particles
            .iter()
            .map(|p| self.project(p.position))
            .collect();
        let mut paths = PathBuilder::new();
        let mut pairs = Vec::with_capacity(8000);
        let max_distance = 8.0 * (1.0 + audio * 0.5);
        'connections: for i in (0..COUNT).step_by(3) {
            for j in (i + 3..COUNT).step_by(3) {
                let a = self.particles[i].position;
                let b = self.particles[j].position;
                if (0..3).map(|axis| (a[axis] - b[axis]).powi(2)).sum::<f32>()
                    < max_distance * max_distance
                {
                    paths.move_to(projected[i].0, projected[i].1);
                    paths.line_to(projected[j].0, projected[j].1);
                    pairs.push((a, b));
                    if pairs.len() == 8000 {
                        break 'connections;
                    }
                }
            }
        }
        if let Some(path) = paths.finish() {
            let mut paint = Paint::default();
            paint.set_color_rgba8(
                self.color[0] as u8,
                self.color[1] as u8,
                self.color[2] as u8,
                (self.line_amount * 0.12 * 255.0) as u8,
            );
            paint.blend_mode = BlendMode::Plus;
            canvas.stroke_path(
                &path,
                &paint,
                &Stroke {
                    width: 0.8,
                    ..Stroke::default()
                },
                Transform::identity(),
                None,
            );
        }
        if matches!(self.state.as_str(), "processing" | "thinking")
            && self.electrons.len() < 3
            && self.time - self.last_electron > 1.0
            && !pairs.is_empty()
        {
            let index = (random(&mut self.seed) * pairs.len().min(500) as f32) as usize;
            let (start, end) = pairs[index];
            self.electrons.push(Electron {
                start,
                end,
                progress: 0.0,
                speed: 0.003 + random(&mut self.seed) * 0.003,
            });
            self.last_electron = self.time;
        }
        for &(x, y, perspective) in &projected {
            let size = (self.point_size + audio * 0.05) * perspective * 0.42;
            dot(
                &mut canvas,
                x,
                y,
                size,
                self.color,
                self.brightness + audio * 0.08,
            );
        }
        for electron in &self.electrons {
            let position = std::array::from_fn(|i| {
                electron.start[i] + (electron.end[i] - electron.start[i]) * electron.progress
            });
            let (x, y, perspective) = self.project(position);
            dot(&mut canvas, x, y, 0.4 * perspective, [255.0; 3], 1.0);
        }
        canvas
    }
}

fn dot(canvas: &mut Pixmap, x: f32, y: f32, size: f32, color: Point, opacity: f32) {
    let radius = size.max(0.7);
    let extent = (radius + 1.0).ceil() as i32;
    for py in (y as i32 - extent)..=(y as i32 + extent) {
        for px in (x as i32 - extent)..=(x as i32 + extent) {
            if px < 0 || py < 0 || px >= SIZE as i32 || py >= SIZE as i32 {
                continue;
            }
            let distance = ((px as f32 + 0.5 - x).powi(2) + (py as f32 + 0.5 - y).powi(2)).sqrt();
            let weight = (radius + 0.5 - distance).clamp(0.0, 1.0) * opacity;
            let offset = (py as usize * SIZE as usize + px as usize) * 4;
            for (channel, value) in color.into_iter().enumerate() {
                canvas.data_mut()[offset + channel] =
                    (canvas.data()[offset + channel] as f32 + value * weight).min(255.0) as u8;
            }
        }
    }
}

pub fn attach(app: &AppShell) {
    let orb = RefCell::new(Orb::new());
    let previous = RefCell::new(Instant::now());
    let accumulator = RefCell::new(0.0f32);
    app.on_presence_frame(move |state, _frame, level| {
        let now = Instant::now();
        let elapsed = now
            .duration_since(*previous.borrow())
            .as_secs_f32()
            .min(0.10);
        *previous.borrow_mut() = now;
        let mut remainder = accumulator.borrow_mut();
        *remainder += elapsed;
        let mut orb = orb.borrow_mut();
        while *remainder >= 1.0 / 60.0 {
            orb.step(&state, level);
            *remainder -= 1.0 / 60.0;
        }
        let audio = if state == "speaking" { level } else { 0.0 };
        let canvas = orb.render(audio);
        let buffer = SharedPixelBuffer::clone_from_slice(canvas.data(), SIZE, SIZE);
        Image::from_rgba8_premultiplied(buffer)
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn jarvis_modes_are_finite_and_reactive() {
        let mut orb = Orb::new();
        for state in ["idle", "listening", "processing", "speaking"] {
            for _ in 0..180 {
                orb.step(state, 0.65);
            }
            assert!(
                orb.particles
                    .iter()
                    .all(|p| p.position.iter().all(|value| value.is_finite()))
            );
            let image = orb.render(0.65);
            if state == "processing" {
                assert!(!orb.electrons.is_empty());
            }
            assert_eq!((image.width(), image.height()), (900, 900));
            let folder = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../target/jarvis-reference");
            std::fs::create_dir_all(&folder).unwrap();
            image
                .save_png(folder.join(format!("native-{state}.png")))
                .unwrap();
        }
        let mut quiet = Orb::new();
        let mut speaking = Orb::new();
        for _ in 0..60 {
            quiet.step("speaking", 0.0);
            speaking.step("speaking", 0.9);
        }
        assert_ne!(quiet.particles[0].position, speaking.particles[0].position);
    }
}

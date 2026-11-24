//! Versioned, content-free operational facts and deterministic mission admission.
//! RAM is explicitly scoped: worker RSS does not include the model provider.
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct MemorySnapshot {
    pub current_process_rss_bytes: Option<u64>,
    pub host_available_ram_bytes: Option<u64>,
    pub host_total_ram_bytes: Option<u64>,
    pub gpu_available: Option<bool>,
    pub vram_bytes: Option<u64>,
    pub gpu_global_used_bytes: Option<u64>,
    pub gpu_global_total_bytes: Option<u64>,
    pub gpu_diagnosis: String,
}

fn gpu_snapshot(result: &mut MemorySnapshot) {
    use std::{
        io::Read,
        process::{Command, Stdio},
        time::{Duration, Instant},
    };
    result.gpu_diagnosis = "sampler_unavailable".into();
    #[cfg(windows)]
    let candidates = [
        std::path::PathBuf::from(r"C:\Windows\System32\nvidia-smi.exe"),
        std::path::PathBuf::from(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"),
    ];
    #[cfg(not(windows))]
    let candidates = [
        std::path::PathBuf::from("/usr/bin/nvidia-smi"),
        std::path::PathBuf::from("/usr/local/bin/nvidia-smi"),
    ];
    let Some(program) = candidates.iter().find(|path| path.is_file()) else {
        return;
    };
    let mut command = Command::new(program);
    command
        .args([
            "--query-gpu=memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000);
    }
    let Ok(mut child) = command.spawn() else {
        result.gpu_diagnosis = "sampler_failed".into();
        return;
    };
    let started = Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(status)) if status.success() => break,
            Ok(Some(_)) | Err(_) => {
                let _ = child.kill();
                let _ = child.wait();
                result.gpu_diagnosis = "sampler_failed".into();
                return;
            }
            Ok(None) if started.elapsed() < Duration::from_millis(1000) => {
                std::thread::sleep(Duration::from_millis(10))
            }
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                result.gpu_diagnosis = "sampler_timeout".into();
                return;
            }
        }
    }
    let mut data = String::new();
    if child
        .stdout
        .take()
        .is_none_or(|stream| stream.take(4097).read_to_string(&mut data).is_err())
    {
        result.gpu_diagnosis = "sampler_failed".into();
        return;
    }
    if let Some((used, total)) = parse_gpu_memory(&data) {
        result.gpu_available = Some(true);
        result.gpu_global_used_bytes = Some(used);
        result.gpu_global_total_bytes = Some(total);
        result.gpu_diagnosis = "measured_global_device_usage".into();
    } else {
        result.gpu_diagnosis = "sampler_failed".into();
    }
}

fn parse_gpu_memory(data: &str) -> Option<(u64, u64)> {
    if data.is_empty() || data.len() > 4096 {
        return None;
    }
    let (mut used, mut total) = (0_u64, 0_u64);
    for line in data.lines() {
        let fields: Vec<_> = line.split(',').map(str::trim).collect();
        if fields.len() != 2 {
            return None;
        }
        let row_used = fields[0].parse::<u64>().ok()?.checked_mul(1024 * 1024)?;
        let row_total = fields[1].parse::<u64>().ok()?.checked_mul(1024 * 1024)?;
        if row_used > row_total || row_total == 0 {
            return None;
        }
        used = used.checked_add(row_used)?;
        total = total.checked_add(row_total)?;
    }
    Some((used, total))
}

/// GPU sampling uses a bounded OS-installed nvidia-smi query. Its memory scope
/// is all devices/processes, never provider or mission allocation.
pub(crate) fn memory_snapshot() -> MemorySnapshot {
    #[cfg(windows)]
    {
        #[repr(C)]
        #[derive(Default)]
        struct MemoryStatus {
            length: u32,
            load: u32,
            total_phys: u64,
            avail_phys: u64,
            total_page: u64,
            avail_page: u64,
            total_virtual: u64,
            avail_virtual: u64,
            avail_extended: u64,
        }
        #[repr(C)]
        #[derive(Default)]
        struct ProcessMemory {
            cb: u32,
            faults: u32,
            peak: usize,
            working_set: usize,
            peak_paged: usize,
            paged: usize,
            peak_nonpaged: usize,
            nonpaged: usize,
            pagefile: usize,
            peak_pagefile: usize,
        }
        #[link(name = "kernel32")]
        unsafe extern "system" {
            fn GlobalMemoryStatusEx(status: *mut MemoryStatus) -> i32;
            fn GetCurrentProcess() -> *mut std::ffi::c_void;
        }
        #[link(name = "psapi")]
        unsafe extern "system" {
            fn GetProcessMemoryInfo(
                process: *mut std::ffi::c_void,
                counters: *mut ProcessMemory,
                size: u32,
            ) -> i32;
        }
        let mut result = MemorySnapshot::default();
        let mut status = MemoryStatus {
            length: std::mem::size_of::<MemoryStatus>() as u32,
            ..MemoryStatus::default()
        };
        let mut process = ProcessMemory {
            cb: std::mem::size_of::<ProcessMemory>() as u32,
            ..ProcessMemory::default()
        };
        unsafe {
            if GlobalMemoryStatusEx(&mut status) != 0 {
                result.host_available_ram_bytes = Some(status.avail_phys);
                result.host_total_ram_bytes = Some(status.total_phys);
            }
            if GetProcessMemoryInfo(
                GetCurrentProcess(),
                &mut process,
                std::mem::size_of::<ProcessMemory>() as u32,
            ) != 0
            {
                result.current_process_rss_bytes = Some(process.working_set as u64);
            }
        }
        gpu_snapshot(&mut result);
        return result;
    }
    #[cfg(target_os = "linux")]
    {
        let mut result = MemorySnapshot::default();
        if let Ok(raw) = std::fs::read_to_string("/proc/meminfo") {
            for line in raw.lines() {
                let mut fields = line.split_whitespace();
                let key = fields.next();
                let value = fields
                    .next()
                    .and_then(|value| value.parse::<u64>().ok())
                    .and_then(|value| value.checked_mul(1024));
                match key {
                    Some("MemTotal:") => result.host_total_ram_bytes = value,
                    Some("MemAvailable:") => result.host_available_ram_bytes = value,
                    _ => {}
                }
            }
        }
        if let Ok(raw) = std::fs::read_to_string("/proc/self/status") {
            result.current_process_rss_bytes = raw.lines().find_map(|line| {
                line.strip_prefix("VmRSS:")?
                    .split_whitespace()
                    .next()?
                    .parse::<u64>()
                    .ok()?
                    .checked_mul(1024)
            });
        }
        gpu_snapshot(&mut result);
        return result;
    }
    #[cfg(not(any(windows, target_os = "linux")))]
    {
        let mut result = MemorySnapshot::default();
        gpu_snapshot(&mut result);
        result
    }
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct WorkerMetrics {
    pub version: u32,
    pub phases_ms: BTreeMap<String, u64>,
    pub input_tokens: Option<u64>,
    pub output_tokens: Option<u64>,
    pub worker_rss_bytes: Option<u64>,
    pub provider_ram_bytes: Option<u64>,
    pub gpu_available: Option<bool>,
    pub vram_bytes: Option<u64>,
    pub inference_calls: Option<u64>,
    pub remote_inference_calls: Option<u64>,
    pub remote_cost_microunits: Option<u64>,
    pub retries: Option<u64>,
    pub residency: String,
    pub response_cache: String,
}

impl WorkerMetrics {
    pub(crate) fn unavailable() -> Self {
        Self {
            version: 1,
            residency: "unavailable".into(),
            response_cache: "unavailable".into(),
            ..Self::default()
        }
    }
    pub(crate) fn parse(value: &serde_json::Value) -> Result<Self, String> {
        let metrics: Self = serde_json::from_value(value.clone()).map_err(|_| "worker_protocol")?;
        let phases = [
            "validation",
            "model_acquisition",
            "inference",
            "model_cleanup",
            "provider_total",
            "worker_total",
        ];
        if metrics.version != 1
            || metrics
                .phases_ms
                .iter()
                .any(|(key, value)| !phases.contains(&key.as_str()) || *value > 180_000)
            || ![
                "unavailable",
                "management_disabled",
                "reused_operator_instance",
                "acquired_owned_instance",
            ]
            .contains(&metrics.residency.as_str())
            || !["disabled", "unavailable"].contains(&metrics.response_cache.as_str())
            || metrics.remote_inference_calls != Some(0)
            || metrics.remote_cost_microunits != Some(0)
            || [
                metrics.input_tokens,
                metrics.output_tokens,
                metrics.worker_rss_bytes,
                metrics.provider_ram_bytes,
                metrics.vram_bytes,
                metrics.inference_calls,
                metrics.retries,
            ]
            .into_iter()
            .flatten()
            .any(|value| value > (1_u64 << 53) - 1)
        {
            return Err("worker_protocol".into());
        }
        Ok(metrics)
    }
    pub(crate) fn total_tokens(&self) -> Option<u64> {
        self.input_tokens?.checked_add(self.output_tokens?)
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct MissionBudget {
    pub elapsed_ms: u64,
    pub tokens: Option<u64>,
    pub inference_calls: u64,
    pub ram_bytes: Option<u64>,
    pub vram_bytes: Option<u64>,
}
impl Default for MissionBudget {
    fn default() -> Self {
        Self {
            elapsed_ms: 1_800_000,
            tokens: None,
            inference_calls: 64,
            ram_bytes: None,
            vram_bytes: None,
        }
    }
}
#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct MissionUsage {
    pub elapsed_ms: u64,
    pub known_tokens: u64,
    pub attempts: u64,
    pub inference_calls: u64,
    pub unknown_token_attempts: u64,
    pub unknown_call_attempts: u64,
    pub peak_worker_rss_bytes: Option<u64>,
    pub peak_provider_ram_bytes: Option<u64>,
    pub peak_vram_bytes: Option<u64>,
    pub remote_inference_calls: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum Admission {
    Allowed,
    TimeExhausted,
    TokensExhausted,
    CallsExhausted,
    TokenCounterUnavailable,
    CallCounterUnavailable,
    RamUnavailable,
    RamExhausted,
    VramUnavailable,
    VramExhausted,
    RemoteInferenceBlocked,
}

impl MissionBudget {
    /// Requested timeout reserves the entire next call. A finite total-token
    /// cap fails closed until tokenizer-backed input bounds are available.
    pub(crate) fn admit(
        &self,
        usage: &MissionUsage,
        timeout_ms: u64,
        remote: bool,
        provider_ram: Option<u64>,
        vram: Option<u64>,
    ) -> Admission {
        if remote || usage.remote_inference_calls > 0 {
            return Admission::RemoteInferenceBlocked;
        }
        if usage.elapsed_ms.saturating_add(timeout_ms) > self.elapsed_ms {
            return Admission::TimeExhausted;
        }
        if usage.inference_calls >= self.inference_calls || usage.attempts >= self.inference_calls {
            return Admission::CallsExhausted;
        }
        if let Some(limit) = self.tokens {
            if usage.unknown_token_attempts > 0 {
                return Admission::TokenCounterUnavailable;
            }
            if usage.known_tokens >= limit {
                return Admission::TokensExhausted;
            }
            // The provider exposes actual tokens only after inference. Without
            // a tokenizer-backed input upper bound, a strict total cap cannot
            // safely admit even the first call.
            return Admission::TokenCounterUnavailable;
        }
        if let Some(limit) = self.ram_bytes {
            match provider_ram {
                None => return Admission::RamUnavailable,
                Some(value) if value > limit => return Admission::RamExhausted,
                _ => {}
            }
        }
        if let Some(limit) = self.vram_bytes {
            match vram {
                None => return Admission::VramUnavailable,
                Some(value) if value > limit => return Admission::VramExhausted,
                _ => {}
            }
        }
        Admission::Allowed
    }
}
fn peak(old: Option<u64>, new: Option<u64>) -> Option<u64> {
    match (old, new) {
        (Some(a), Some(b)) => Some(a.max(b)),
        (a, b) => a.or(b),
    }
}
impl MissionUsage {
    /// Record exactly once per persisted attempt; the owning store provides
    /// attempt-id uniqueness. Wall time is supplied by Core's monotonic clock.
    pub(crate) fn record(&mut self, metrics: &WorkerMetrics, elapsed_ms: u64) {
        self.attempts = self.attempts.saturating_add(1);
        self.elapsed_ms = self.elapsed_ms.saturating_add(elapsed_ms);
        match metrics.total_tokens() {
            Some(tokens) => self.known_tokens = self.known_tokens.saturating_add(tokens),
            None => self.unknown_token_attempts = self.unknown_token_attempts.saturating_add(1),
        }
        match metrics.inference_calls {
            Some(calls) => self.inference_calls = self.inference_calls.saturating_add(calls),
            None => self.unknown_call_attempts = self.unknown_call_attempts.saturating_add(1),
        }
        self.remote_inference_calls = self
            .remote_inference_calls
            .saturating_add(metrics.remote_inference_calls.unwrap_or(0));
        self.peak_worker_rss_bytes = peak(self.peak_worker_rss_bytes, metrics.worker_rss_bytes);
        self.peak_provider_ram_bytes =
            peak(self.peak_provider_ram_bytes, metrics.provider_ram_bytes);
        self.peak_vram_bytes = peak(self.peak_vram_bytes, metrics.vram_bytes);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn unknown_counters_are_not_measured_zero() {
        let metrics = WorkerMetrics::unavailable();
        assert_eq!(metrics.total_tokens(), None);
        let mut usage = MissionUsage::default();
        usage.record(&metrics, 20);
        assert_eq!(usage.unknown_token_attempts, 1);
        assert_eq!(usage.peak_vram_bytes, None);
        assert_eq!(
            MissionBudget::default().admit(&usage, 100, false, None, None),
            Admission::Allowed
        );
    }
    #[test]
    fn deterministic_caps_and_local_only() {
        let mut budget = MissionBudget {
            elapsed_ms: 1000,
            tokens: None,
            inference_calls: 2,
            ram_bytes: Some(100),
            vram_bytes: Some(50),
        };
        let mut usage = MissionUsage::default();
        assert_eq!(
            budget.admit(&usage, 100, true, Some(1), Some(1)),
            Admission::RemoteInferenceBlocked
        );
        assert_eq!(
            budget.admit(&usage, 1001, false, Some(1), Some(1)),
            Admission::TimeExhausted
        );
        assert_eq!(
            budget.admit(&usage, 100, false, None, Some(1)),
            Admission::RamUnavailable
        );
        assert_eq!(
            budget.admit(&usage, 100, false, Some(101), Some(1)),
            Admission::RamExhausted
        );
        assert_eq!(
            budget.admit(&usage, 100, false, Some(1), None),
            Admission::VramUnavailable
        );
        assert_eq!(
            budget.admit(&usage, 100, false, Some(1), Some(51)),
            Admission::VramExhausted
        );
        assert_eq!(
            budget.admit(&usage, 100, false, Some(1), Some(1)),
            Admission::Allowed
        );
        budget.tokens = Some(20);
        assert_eq!(
            budget.admit(&usage, 100, false, Some(1), Some(1)),
            Admission::TokenCounterUnavailable
        );
        usage.known_tokens = 20;
        assert_eq!(
            budget.admit(&usage, 100, false, Some(1), Some(1)),
            Admission::TokensExhausted
        );
        usage.known_tokens = 0;
        usage.inference_calls = 2;
        assert_eq!(
            budget.admit(&usage, 100, false, Some(1), Some(1)),
            Admission::CallsExhausted
        );
    }
    #[test]
    fn gpu_global_sampler_rejects_unavailable_and_keeps_scope() {
        assert_eq!(
            parse_gpu_memory("12, 4096\n"),
            Some((12 * 1024 * 1024, 4096 * 1024 * 1024))
        );
        assert_eq!(parse_gpu_memory("N/A, 4096\n"), None);
        assert_eq!(parse_gpu_memory("-1, 4096\n"), None);
        assert_eq!(parse_gpu_memory("5000, 4096\n"), None);
        assert_eq!(parse_gpu_memory(""), None);
    }
    #[test]
    #[cfg(any(windows, target_os = "linux"))]
    fn native_snapshot_scopes_memory_and_does_not_invent_provider_vram() {
        let snapshot = memory_snapshot();
        assert!(
            snapshot
                .current_process_rss_bytes
                .is_some_and(|value| value > 0)
        );
        assert!(snapshot.host_total_ram_bytes.is_some_and(|value| value > 0));
        assert!(snapshot.host_available_ram_bytes <= snapshot.host_total_ram_bytes);
        assert_eq!(snapshot.vram_bytes, None);
        assert!(!snapshot.gpu_diagnosis.is_empty());
    }
    #[test]
    fn metric_schema_rejects_private_or_unbounded_diagnostics() {
        let mut value = serde_json::to_value(WorkerMetrics::unavailable()).unwrap();
        value["prompt"] = serde_json::json!("CANARY-secret");
        assert!(WorkerMetrics::parse(&value).is_err());
        value.as_object_mut().unwrap().remove("prompt");
        value["remote_inference_calls"] = serde_json::json!(0);
        value["remote_cost_microunits"] = serde_json::json!(0);
        assert!(WorkerMetrics::parse(&value).is_ok());
        value["phases_ms"]["CANARY-secret"] = serde_json::json!(1);
        assert!(WorkerMetrics::parse(&value).is_err());
    }
}

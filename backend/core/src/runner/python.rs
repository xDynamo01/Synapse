//! Fixed offline Python check phases. Core owns all staged paths and the profile.
use std::path::Path;

use super::{
    Control,
    windows::{Profile, Receipt},
};

const COMPILE: &str =
    "import py_compile, sys; py_compile.compile(sys.argv[1], cfile=sys.argv[2], doraise=True)";
const RUN_TESTS: &str = r#"
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

source, temporary = sys.argv[1:]
tempfile.tempdir = temporary
sys.path.insert(0, str(Path(source).parent))

spec = importlib.util.spec_from_file_location("_synapse_project_tests", source)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
suite = unittest.defaultTestLoader.loadTestsFromModule(module)
if suite.countTestCases() == 0:
    sys.exit("no unittest tests found")
result = unittest.TextTestRunner().run(suite)
sys.exit(not result.wasSuccessful())
"#;

pub(super) fn run(
    profile: &Profile,
    interpreter: &Path,
    project: &Path,
    entrypoint: &Path,
    output: &Path,
    temporary: &Path,
    control: &Control,
) -> Result<Vec<Receipt>, String> {
    if entrypoint.file_name() != Some(entrypoint.as_os_str())
        || entrypoint.extension().and_then(|value| value.to_str()) != Some("py")
    {
        return Err("python_entrypoint".into());
    }
    let source = project.join(entrypoint);
    let bytecode = output.join("check.pyc");
    let launch = |script, paths: [&Path; 2]| {
        let mut args = ["-I", "-S", "-B", "-c", script].map(str::to_owned).to_vec();
        for path in paths {
            args.push(path.to_str().ok_or("invalid_python_check_path")?.to_owned());
        }
        profile.launch(interpreter, &args, project, temporary, control)
    };

    let compile = launch(COMPILE, [&source, &bytecode])?;
    if compile.exit_code != 0 {
        return Ok(vec![compile]);
    }
    let tests = launch(RUN_TESTS, [&source, temporary])?;
    Ok(vec![compile, tests])
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::*;
    use crate::runner::assets;

    #[test]
    #[ignore = "requires a locally built dedicated Python runtime"]
    fn dedicated_runtime_checks_pass_failure_and_empty_suite() {
        let configured = std::env::var_os("SYNAPSE_CHECK_PYTHON_EXECUTABLE")
            .expect("set SYNAPSE_CHECK_PYTHON_EXECUTABLE to the dedicated runtime");
        let current = std::env::current_dir().unwrap();
        let root = tempfile::TempDir::new_in(current.ancestors().last().unwrap()).unwrap();
        let name = root
            .path()
            .file_name()
            .unwrap()
            .to_string_lossy()
            .replace('.', "");
        let profile = Profile::create(&format!("Synapse.Python.{name}")).unwrap();
        let runtime = root.path().join("runtime");
        let project = root.path().join("project");
        let output = root.path().join("output");
        let temporary = root.path().join("temporary");
        for path in [&runtime, &project, &output, &temporary] {
            fs::create_dir(path).unwrap();
        }
        profile.protect(root.path(), false).unwrap();
        for path in [&runtime, &project] {
            profile.protect(path, false).unwrap();
        }
        for path in [&output, &temporary] {
            profile.protect(path, true).unwrap();
        }

        let control = Control::new();
        let interpreter = assets::python(Path::new(&configured), &runtime, &control).unwrap();
        fs::write(
            project.join("test_pass.py"),
            r#"
import array
import sqlite3
import tempfile
import unittest

class Arithmetic(unittest.TestCase):
    def test_addition(self):
        self.assertEqual(sum(array.array("i", [2, 3])), 5)
        with sqlite3.connect(":memory:") as db:
            self.assertEqual(db.execute("SELECT 2 + 3").fetchone(), (5,))
        with tempfile.TemporaryFile() as handle:
            handle.write(b"local")
            handle.seek(0)
            self.assertEqual(handle.read(), b"local")
"#,
        )
        .unwrap();
        fs::write(
            project.join("test_fail.py"),
            r#"
import unittest

class Failure(unittest.TestCase):
    def test_intentional_failure(self):
        self.assertEqual(2 + 3, 6)
"#,
        )
        .unwrap();
        fs::write(project.join("test_empty.py"), "value = 5\n").unwrap();
        fs::write(project.join("test_syntax.py"), "def\n").unwrap();

        let check = |file| {
            run(
                &profile,
                &interpreter,
                &project,
                Path::new(file),
                &output,
                &temporary,
                &control,
            )
        };
        let pass = check("test_pass.py");
        let fail = check("test_fail.py");
        let empty = check("test_empty.py");
        let syntax = check("test_syntax.py");
        profile.remove().unwrap();

        for (result, exit_codes, diagnostic) in [
            (pass, &[0, 0][..], "OK"),
            (fail, &[0, 1][..], "AssertionError"),
            (empty, &[0, 1][..], "no unittest tests found"),
            (syntax, &[1][..], "SyntaxError"),
        ] {
            let receipts = result.unwrap();
            eprintln!("Python check receipts: {receipts:?}");
            assert_eq!(
                receipts
                    .iter()
                    .map(|phase| phase.exit_code)
                    .collect::<Vec<_>>(),
                exit_codes
            );
            assert!(receipts.last().unwrap().output.contains(diagnostic));
            for receipt in receipts {
                assert!(receipt.token.lpac && receipt.token.job);
                assert_eq!(receipt.token.capabilities, 0);
            }
        }
    }
}

"""Runtime Python entrypoint observations captured inside the existing Lab sandbox."""

import json
import os
import sys


def _argv(value):
    if (
        not isinstance(value, (list, tuple))
        or len(value) > 256
        or any(not isinstance(item, str) or "\x00" in item for item in value)
        or sum(len(item.encode("utf-8")) for item in value) > 65536
    ):
        return None
    return list(value)


class EntrypointCapture:
    """Remember startup state before the target can change cwd or sys.argv.

    These fields are process observations, not authenticated evidence against a
    deliberately falsifying target. No target module is imported or executed here.
    """

    def __init__(self):
        self.pid = os.getpid()
        self.ppid = os.getppid()
        self.startup_cwd = os.getcwd()
        self.orig_argv = _argv(getattr(sys, "orig_argv", None))
        self.startup_argv = _argv(sys.argv)
        self.executable = sys.executable
        self.argv_override = self._apply_override()
        self.effective_startup_argv = _argv(sys.argv)
        self.main_file = None
        self.module = None
        self._previous_profile = sys.getprofile()
        self._observer = None
        self.profile_observation = "awaiting_main"
        if self._previous_profile is not None and not callable(self._previous_profile):
            # cProfile objects cannot be passed back to sys.setprofile. Leave the
            # existing profiler intact and report that this observation is unavailable.
            self.profile_observation = "existing_profiler_unsupported"
            return

        def observe(frame, event, argument):
            if (
                event == "call"
                and frame.f_code.co_name == "<module>"
                and frame.f_globals.get("__name__") == "__main__"
            ):
                main_file = frame.f_globals.get("__file__")
                module = getattr(frame.f_globals.get("__spec__"), "name", None)
                self.main_file = main_file if isinstance(main_file, str) else None
                self.module = module if isinstance(module, str) else None
                self.profile_observation = "main_frame_observed"
                self.close()
            if callable(self._previous_profile):
                self._previous_profile(frame, event, argument)

        self._observer = observe
        sys.setprofile(observe)

    def close(self):
        if self._observer is not None and sys.getprofile() is self._observer:
            sys.setprofile(self._previous_profile)

    def _apply_override(self):
        raw = os.environ.get("HEADROOM_TARGET_ARGV_OVERRIDE")
        original = self.startup_argv[1:] if self.startup_argv else None
        result = {
            "requested": raw is not None,
            "matched": False,
            "applied": False,
            "original_target_args": original,
            "effective_target_args": original,
            "reason": "not_requested",
        }
        if raw is None:
            return result
        try:
            if len(raw.encode("utf-8")) > 131072:
                raise ValueError("override too large")
            proposal = json.loads(raw)
            required = {
                "expected_startup_cwd",
                "expected_orig_argv",
                "original_target_args",
                "effective_target_args",
            }
            if not isinstance(proposal, dict) or set(proposal) != required:
                raise ValueError("invalid override fields")
            effective = _argv(proposal["effective_target_args"])
            if effective is None or len(effective) > 100:
                raise ValueError("invalid effective argv")
        except (ValueError, TypeError):
            result["reason"] = "invalid_override"
            return result
        matched = (
            proposal["expected_startup_cwd"] == self.startup_cwd
            and proposal["expected_orig_argv"] == self.orig_argv
            and proposal["original_target_args"] == original
        )
        result["matched"] = matched
        if matched:
            sys.argv[1:] = effective
            result.update(
                applied=True, effective_target_args=effective, reason="matched_before_main"
            )
        else:
            result["reason"] = "different_python_entrypoint"
        return result

    def finish(self):
        main = sys.modules.get("__main__")
        self.close()
        main_file = self.main_file or getattr(main, "__file__", None)
        spec = getattr(main, "__spec__", None)
        module = self.module if self.main_file else getattr(spec, "name", None)
        if isinstance(main_file, str) and not os.path.isabs(main_file):
            main_file = os.path.normpath(os.path.join(self.startup_cwd, main_file))
        if not isinstance(main_file, str) or len(main_file) > 4096 or "\x00" in main_file:
            main_file = None
        if module is not None and (not isinstance(module, str) or len(module) > 4096):
            module = None
        try:
            cwd = os.getcwd()
        except OSError:
            cwd = None
        argv = _argv(sys.argv)
        complete = (
            os.getpid() == self.pid
            and self.profile_observation != "existing_profiler_unsupported"
            and main_file is not None
            and self.orig_argv is not None
            and self.startup_argv is not None
            and argv is not None
        )
        return {
            "schema_version": 1,
            "complete": complete,
            "pid": self.pid,
            "ppid": self.ppid,
            "executable": self.executable,
            "startup_cwd": self.startup_cwd,
            "cwd": cwd,
            "orig_argv": self.orig_argv,
            "startup_argv": self.startup_argv,
            "effective_startup_argv": self.effective_startup_argv,
            "argv_override": self.argv_override,
            "argv": argv,
            "main_file": main_file,
            "module": module,
            "entry_observation": self.profile_observation,
        }

from scripts.audit_runtime_lifecycle import cli_contract


def test_unknown_service_flag_is_a_contract_failure():
    caller = '''
def run():
    command = [python, str(ROOT / "runner.py"), "--input", source]
    command.extend(["--retired-option", "0"])
'''
    target = 'parser.add_argument("--input")'
    report = cli_contract(caller, target, "runner.py")
    assert report["status"] == "UNSUPPORTED_OPTIONS"
    assert report["unsupported"] == ["--retired-option"]
    assert report["runtime_execution_verified"] is False


def test_other_subprocess_options_do_not_contaminate_the_contract():
    caller = '''
def run():
    command = [python, "runner.py", "--input", source]
    recovery = [python, "repair.py", "--repair-only"]
    recovery.append("--repair-force")
'''
    report = cli_contract(caller, 'parser.add_argument("--input")', "runner.py")
    assert report["status"] == "STATIC_OPTIONS_MATCH"
    assert report["passed"] == ["--input"]


def test_missing_caller_is_not_a_passing_wiring_check():
    assert cli_contract("pass", 'parser.add_argument("--input")', "runner.py")["status"] == "CALLER_NOT_FOUND"

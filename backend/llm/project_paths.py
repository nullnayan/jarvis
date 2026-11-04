"""Literal file-path validation for the approved local project runner."""
import ast
import ntpath
import os


def validate_project_paths(code: str, project_dir: str) -> tuple[bool, str]:
    if not code or not code.strip():
        return False, "empty code"
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return False, f"syntax error: {exc.msg}"
    root = os.path.normcase(os.path.realpath(project_dir))
    operations = {"open", "Path", "remove", "unlink", "rmdir", "mkdir", "makedirs", "chdir", "rename", "replace", "copy", "copy2", "move"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
        if name not in operations:
            continue
        # Rename/copy/move have both source and destination paths.
        count = 2 if name in {"rename", "replace", "copy", "copy2", "move"} else 1
        for argument in node.args[:count]:
            if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
                continue
            value = argument.value
            if ntpath.isabs(value) and not os.path.isabs(value):
                return False, "foreign absolute file path"
            target = os.path.normcase(os.path.realpath(os.path.join(root, value)))
            try:
                if os.path.commonpath([root, target]) != root:
                    return False, "file path escapes project directory"
            except ValueError:
                return False, "file path is on another drive"
    return True, ""

"""Tests for svg_text2path.tools.dependencies module.

Coverage: 10 tests covering enums, dataclasses, package checking, tool checking,
version comparison, and full dependency verification.
All tests use real dependencies and tools - no mocking.
"""

from pathlib import Path

import pytest

from svg_text2path.tools.dependencies import (
    DependencyInfo,
    DependencyReport,
    DependencyStatus,
    DependencyType,
    _version_satisfies,
    check_python_package,
    check_system_tool,
    verify_all_dependencies,
)


class TestDependencyTypeEnum:
    """Tests for DependencyType enum values."""

    def test_dependency_type_python_package_value(self) -> None:
        """DependencyType.PYTHON_PACKAGE has correct string value."""
        assert DependencyType.PYTHON_PACKAGE.value == "python"

    def test_dependency_type_system_tool_value(self) -> None:
        """DependencyType.SYSTEM_TOOL has correct string value."""
        assert DependencyType.SYSTEM_TOOL.value == "system"

    def test_dependency_type_npm_package_value(self) -> None:
        """DependencyType.NPM_PACKAGE has correct string value."""
        assert DependencyType.NPM_PACKAGE.value == "npm"

    def test_dependency_type_all_members_defined(self) -> None:
        """DependencyType enum has exactly 3 members."""
        assert len(DependencyType) == 3


class TestDependencyStatusEnum:
    """Tests for DependencyStatus enum values."""

    def test_dependency_status_ok_value(self) -> None:
        """DependencyStatus.OK has correct string value."""
        assert DependencyStatus.OK.value == "ok"

    def test_dependency_status_missing_value(self) -> None:
        """DependencyStatus.MISSING has correct string value."""
        assert DependencyStatus.MISSING.value == "missing"

    def test_dependency_status_version_mismatch_value(self) -> None:
        """DependencyStatus.VERSION_MISMATCH has correct string value."""
        assert DependencyStatus.VERSION_MISMATCH.value == "version_mismatch"

    def test_dependency_status_error_value(self) -> None:
        """DependencyStatus.ERROR has correct string value."""
        assert DependencyStatus.ERROR.value == "error"

    def test_dependency_status_all_members_defined(self) -> None:
        """DependencyStatus enum has exactly 4 members."""
        assert len(DependencyStatus) == 4


class TestDependencyInfoDataclass:
    """Tests for DependencyInfo dataclass initialization and defaults."""

    def test_dependency_info_required_fields(self) -> None:
        """DependencyInfo initializes with required fields correctly."""
        info = DependencyInfo(
            name="test-package",
            dep_type=DependencyType.PYTHON_PACKAGE,
            required=True,
        )
        assert info.name == "test-package"
        assert info.dep_type == DependencyType.PYTHON_PACKAGE
        assert info.required is True

    def test_dependency_info_default_status_is_missing(self) -> None:
        """DependencyInfo default status is MISSING."""
        info = DependencyInfo(
            name="test",
            dep_type=DependencyType.PYTHON_PACKAGE,
            required=True,
        )
        assert info.status == DependencyStatus.MISSING

    def test_dependency_info_default_optional_fields_are_none(self) -> None:
        """DependencyInfo optional fields default to None or empty string."""
        info = DependencyInfo(
            name="test",
            dep_type=DependencyType.SYSTEM_TOOL,
            required=False,
        )
        assert info.version is None
        assert info.min_version is None
        assert info.path is None
        assert info.error is None
        assert info.install_hint == ""
        assert info.feature == ""

    def test_dependency_info_all_fields_populated(self) -> None:
        """DependencyInfo accepts all fields when provided."""
        info = DependencyInfo(
            name="my-tool",
            dep_type=DependencyType.SYSTEM_TOOL,
            required=False,
            status=DependencyStatus.OK,
            version="1.2.3",
            min_version="1.0.0",
            path=Path("/usr/bin/my-tool"),
            error=None,
            install_hint="brew install my-tool",
            feature="Special feature",
        )
        assert info.name == "my-tool"
        assert info.version == "1.2.3"
        assert info.min_version == "1.0.0"
        assert info.path == Path("/usr/bin/my-tool")
        assert info.install_hint == "brew install my-tool"
        assert info.feature == "Special feature"


class TestDependencyReportDataclass:
    """Tests for DependencyReport dataclass properties."""

    @pytest.fixture
    def sample_report(self) -> DependencyReport:
        """Create a sample DependencyReport with mixed statuses."""
        return DependencyReport(
            python_packages=[
                DependencyInfo(
                    name="installed-pkg",
                    dep_type=DependencyType.PYTHON_PACKAGE,
                    required=True,
                    status=DependencyStatus.OK,
                ),
                DependencyInfo(
                    name="missing-required-pkg",
                    dep_type=DependencyType.PYTHON_PACKAGE,
                    required=True,
                    status=DependencyStatus.MISSING,
                ),
                DependencyInfo(
                    name="missing-optional-pkg",
                    dep_type=DependencyType.PYTHON_PACKAGE,
                    required=False,
                    status=DependencyStatus.MISSING,
                ),
            ],
            system_tools=[
                DependencyInfo(
                    name="installed-tool",
                    dep_type=DependencyType.SYSTEM_TOOL,
                    required=False,
                    status=DependencyStatus.OK,
                ),
            ],
            npm_packages=[
                DependencyInfo(
                    name="missing-npm",
                    dep_type=DependencyType.NPM_PACKAGE,
                    required=False,
                    status=DependencyStatus.MISSING,
                ),
            ],
        )

    def test_all_dependencies_returns_flat_list(
        self, sample_report: DependencyReport
    ) -> None:
        """all_dependencies property returns all deps as flat list."""
        all_deps = sample_report.all_dependencies
        assert len(all_deps) == 5
        names = [d.name for d in all_deps]
        assert "installed-pkg" in names
        assert "missing-required-pkg" in names
        assert "missing-optional-pkg" in names
        assert "installed-tool" in names
        assert "missing-npm" in names

    def test_missing_required_returns_only_missing_required_deps(
        self, sample_report: DependencyReport
    ) -> None:
        """missing_required property returns only missing required deps."""
        missing_req = sample_report.missing_required
        assert len(missing_req) == 1
        assert missing_req[0].name == "missing-required-pkg"
        assert missing_req[0].required is True

    def test_missing_optional_returns_only_missing_optional_deps(
        self, sample_report: DependencyReport
    ) -> None:
        """missing_optional property returns only missing optional deps."""
        missing_opt = sample_report.missing_optional
        assert len(missing_opt) == 2
        names = [d.name for d in missing_opt]
        assert "missing-optional-pkg" in names
        assert "missing-npm" in names
        for dep in missing_opt:
            assert dep.required is False

    def test_all_required_ok_is_false_when_required_missing(
        self, sample_report: DependencyReport
    ) -> None:
        """all_required_ok returns False when a required dep is missing."""
        assert sample_report.all_required_ok is False

    def test_all_required_ok_is_true_when_all_required_present(self) -> None:
        """all_required_ok returns True when all required deps are OK."""
        report = DependencyReport(
            python_packages=[
                DependencyInfo(
                    name="pkg1",
                    dep_type=DependencyType.PYTHON_PACKAGE,
                    required=True,
                    status=DependencyStatus.OK,
                ),
            ],
            system_tools=[],
            npm_packages=[
                DependencyInfo(
                    name="npm-optional",
                    dep_type=DependencyType.NPM_PACKAGE,
                    required=False,
                    status=DependencyStatus.MISSING,  # Optional missing is OK
                ),
            ],
        )
        assert report.all_required_ok is True

    def test_all_ok_is_false_when_any_dep_missing(
        self, sample_report: DependencyReport
    ) -> None:
        """all_ok returns False when any dependency is not OK."""
        assert sample_report.all_ok is False

    def test_all_ok_is_true_when_all_deps_ok(self) -> None:
        """all_ok returns True when all deps have OK status."""
        report = DependencyReport(
            python_packages=[
                DependencyInfo(
                    name="pkg1",
                    dep_type=DependencyType.PYTHON_PACKAGE,
                    required=True,
                    status=DependencyStatus.OK,
                ),
            ],
            system_tools=[
                DependencyInfo(
                    name="tool1",
                    dep_type=DependencyType.SYSTEM_TOOL,
                    required=False,
                    status=DependencyStatus.OK,
                ),
            ],
            npm_packages=[],
        )
        assert report.all_ok is True

    def test_empty_report_all_ok_is_true(self) -> None:
        """Empty DependencyReport has all_ok=True and all_required_ok=True."""
        empty_report = DependencyReport()
        assert empty_report.all_ok is True
        assert empty_report.all_required_ok is True
        assert empty_report.all_dependencies == []


class TestCheckPythonPackage:
    """Tests for check_python_package function with real packages."""

    def test_check_installed_package_returns_ok_status(self) -> None:
        """check_python_package returns OK for installed package (click)."""
        info = check_python_package("click")
        assert info.status == DependencyStatus.OK
        assert info.name == "click"
        assert info.dep_type == DependencyType.PYTHON_PACKAGE
        assert info.version is not None  # click has __version__

    def test_check_installed_package_with_different_import_name(self) -> None:
        """check_python_package handles packages with different import names."""
        # PIL is imported from pillow package
        info = check_python_package("pillow", import_name="PIL")
        assert info.status == DependencyStatus.OK
        assert info.name == "pillow"

    def test_check_nonexistent_package_returns_missing_status(self) -> None:
        """check_python_package returns MISSING for non-existent package."""
        info = check_python_package("this-package-definitely-does-not-exist-xyz123")
        assert info.status == DependencyStatus.MISSING
        assert info.version is None

    def test_check_package_sets_install_hint(self) -> None:
        """check_python_package sets appropriate install_hint."""
        info = check_python_package("fake-package")
        assert "pip install fake-package" in info.install_hint

    def test_check_package_with_min_version_satisfied(self) -> None:
        """check_python_package returns OK when min_version is satisfied."""
        # click is installed and version should be >= 8.0
        info = check_python_package("click", min_version="1.0.0")
        assert info.status == DependencyStatus.OK

    def test_check_package_with_min_version_not_satisfied(self) -> None:
        """check_python_package returns VERSION_MISMATCH when version too low."""
        # Request an impossibly high version
        info = check_python_package("click", min_version="999.0.0")
        assert info.status == DependencyStatus.VERSION_MISMATCH
        assert "999.0.0" in str(info.error)


class TestCheckSystemTool:
    """Tests for check_system_tool function with real system tools."""

    def test_check_existing_tool_returns_ok_status(self) -> None:
        """check_system_tool returns OK for existing tool (python3)."""
        info = check_system_tool("python3")
        assert info.status == DependencyStatus.OK
        assert info.name == "python3"
        assert info.dep_type == DependencyType.SYSTEM_TOOL
        assert info.path is not None
        assert info.path.exists()

    def test_check_existing_tool_with_custom_command(self) -> None:
        """check_system_tool can use custom command different from name."""
        # Use 'ls' command but name it differently
        info = check_system_tool("list-files", command="ls")
        assert info.status == DependencyStatus.OK
        assert info.name == "list-files"
        assert info.path is not None

    def test_check_nonexistent_tool_returns_missing_status(self) -> None:
        """check_system_tool returns MISSING for non-existent tool."""
        info = check_system_tool("this-tool-definitely-does-not-exist-xyz123")
        assert info.status == DependencyStatus.MISSING
        assert info.path is None

    def test_check_tool_sets_path_when_found(self) -> None:
        """check_system_tool sets path when tool is found."""
        info = check_system_tool("ls")
        assert info.status == DependencyStatus.OK
        assert info.path is not None
        assert isinstance(info.path, Path)
        # On Windows, executable might be ls.EXE, so check stem instead of name
        assert info.path.stem.lower() == "ls"

    def test_check_tool_extracts_version(self) -> None:
        """check_system_tool extracts version from tool output."""
        info = check_system_tool("python3")
        # Python3 should have a version like "3.x.x"
        assert info.version is not None
        assert info.version.startswith("3.")


class TestVersionSatisfies:
    """Tests for _version_satisfies function with various version strings."""

    def test_version_equal_satisfies(self) -> None:
        """Equal versions satisfy requirement."""
        assert _version_satisfies("1.0.0", "1.0.0") is True

    def test_version_greater_satisfies(self) -> None:
        """Greater version satisfies requirement."""
        assert _version_satisfies("2.0.0", "1.0.0") is True
        assert _version_satisfies("1.1.0", "1.0.0") is True
        assert _version_satisfies("1.0.1", "1.0.0") is True

    def test_version_less_does_not_satisfy(self) -> None:
        """Lesser version does not satisfy requirement."""
        assert _version_satisfies("1.0.0", "2.0.0") is False
        assert _version_satisfies("1.0.0", "1.1.0") is False
        assert _version_satisfies("1.0.0", "1.0.1") is False

    def test_version_with_v_prefix_handled(self) -> None:
        """Version strings with 'v' prefix are handled correctly."""
        assert _version_satisfies("v1.2.0", "1.0.0") is True
        assert _version_satisfies("1.2.0", "v1.0.0") is True
        assert _version_satisfies("v1.2.0", "v1.0.0") is True

    def test_version_two_part_padded(self) -> None:
        """Two-part versions are padded and compared correctly."""
        assert _version_satisfies("1.2", "1.0.0") is True
        assert _version_satisfies("1.0.0", "1.2") is False

    def test_version_invalid_returns_true(self) -> None:
        """Invalid version strings return True (fail-safe behavior)."""
        assert _version_satisfies("invalid", "1.0.0") is True
        assert _version_satisfies("1.0.0", "invalid") is True

    def test_version_complex_comparison(self) -> None:
        """Complex version comparisons work correctly."""
        assert _version_satisfies("10.0.0", "9.9.9") is True
        assert _version_satisfies("1.10.0", "1.9.0") is True
        assert _version_satisfies("1.0.10", "1.0.9") is True


class TestVerifyAllDependencies:
    """Tests for verify_all_dependencies function."""

    def test_verify_all_returns_dependency_report(self) -> None:
        """verify_all_dependencies returns a DependencyReport instance."""
        report = verify_all_dependencies()
        assert isinstance(report, DependencyReport)

    def test_verify_all_populates_python_packages(self) -> None:
        """verify_all_dependencies populates python_packages list."""
        report = verify_all_dependencies(check_system=False, check_npm=False)
        assert len(report.python_packages) > 0
        # Check that required packages are included (click and rich are in the list)
        pkg_names = [p.name for p in report.python_packages]
        assert "click" in pkg_names
        assert "rich" in pkg_names

    def test_verify_all_populates_system_tools(self) -> None:
        """verify_all_dependencies populates system_tools list."""
        report = verify_all_dependencies(check_python=False, check_npm=False)
        assert len(report.system_tools) > 0
        # Check expected tools are in the list
        tool_names = [t.name for t in report.system_tools]
        assert "node" in tool_names or "git" in tool_names

    def test_verify_all_respects_check_python_flag(self) -> None:
        """verify_all_dependencies skips Python check when flag is False."""
        report = verify_all_dependencies(check_python=False)
        assert len(report.python_packages) == 0

    def test_verify_all_respects_check_system_flag(self) -> None:
        """verify_all_dependencies skips system check when flag is False."""
        report = verify_all_dependencies(check_system=False)
        assert len(report.system_tools) == 0

    def test_verify_all_respects_check_npm_flag(self) -> None:
        """verify_all_dependencies skips npm check when flag is False."""
        report = verify_all_dependencies(check_npm=False)
        assert len(report.npm_packages) == 0

    def test_verify_all_required_packages_have_status(self) -> None:
        """All verified packages have a valid status set."""
        report = verify_all_dependencies(check_system=False, check_npm=False)
        for pkg in report.python_packages:
            assert pkg.status in (
                DependencyStatus.OK,
                DependencyStatus.MISSING,
                DependencyStatus.VERSION_MISMATCH,
                DependencyStatus.ERROR,
            )

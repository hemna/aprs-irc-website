"""pytest configuration and shared fixtures."""
import os
import sys

import pytest

# Make sure the app directory is on the path so imports resolve without
# installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


@pytest.fixture(scope="session", autouse=True)
def minimal_config(tmp_path_factory):
    """Write a minimal aprsd_irc.conf so create_app() can parse config."""
    cfg_dir = tmp_path_factory.mktemp("config")
    cfg_file = cfg_dir / "aprsd_irc.conf"
    cfg_file.write_text(
        "[DEFAULT]\n"
        "[web]\n"
        "host_ip = 127.0.0.1\n"
        "host_port = 80\n"
    )
    # Patch create_app's hard-coded path before any import of main happens.
    os.environ["APRS_IRC_TEST_CONFIG"] = str(cfg_file)
    return str(cfg_file)


@pytest.fixture
def minimal_config_with_admin(tmp_path):
    """Minimal config with admin_password set to 'testpass'."""
    conf = tmp_path / "test_admin.conf"
    conf.write_text(
        "[DEFAULT]\n"
        "[web]\n"
        "host_ip = 127.0.0.1\n"
        "host_port = 80\n"
        "admin_password = testpass\n"
    )
    return str(conf)

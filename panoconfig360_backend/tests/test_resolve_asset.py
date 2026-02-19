"""
Tests for asset resolution with local and remote fallback.
"""
import os
from pathlib import Path
from unittest.mock import patch, Mock
import pytest


def test_resolve_asset_local_file_exists(tmp_path):
    """Test that resolve_asset finds local files correctly."""
    from panoconfig360_backend.render.vips_compat import resolve_asset
    
    # Create a test file
    test_base = tmp_path / "test_asset"
    test_file = test_base.with_suffix(".jpg")
    test_file.write_text("fake image content")
    
    # Should find the .jpg file
    result = resolve_asset(test_base)
    assert result == test_file
    assert result.exists()


def test_resolve_asset_tries_all_extensions(tmp_path):
    """Test that resolve_asset tries all supported extensions."""
    from panoconfig360_backend.render.vips_compat import resolve_asset
    
    # Create a .png file
    test_base = tmp_path / "test_asset"
    test_file = test_base.with_suffix(".png")
    test_file.write_text("fake image content")
    
    # Should find the .png file
    result = resolve_asset(test_base)
    assert result == test_file


def test_resolve_asset_remote_fallback(tmp_path, monkeypatch):
    """Test that resolve_asset downloads from R2 when file doesn't exist locally."""
    from panoconfig360_backend.render.vips_compat import resolve_asset
    
    # Set R2_PUBLIC_URL
    monkeypatch.setenv("R2_PUBLIC_URL", "https://example.r2.dev")
    
    # Create a path that doesn't exist locally but matches R2 structure
    test_base = tmp_path / "panoconfig360_cache" / "clients" / "test" / "base_test"
    
    # Mock requests.get to simulate successful download
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.iter_content = Mock(return_value=[b"fake downloaded image"])
    
    with patch("panoconfig360_backend.render.vips_compat.requests.get", return_value=mock_response) as mock_get:
        result = resolve_asset(test_base)
        
        # Verify it attempted to download
        assert mock_get.called
        # Verify the URL construction
        call_args = mock_get.call_args
        assert "clients/test/base_test" in call_args[0][0]
        
        # Verify the file was created
        assert result.exists()
        assert result.read_bytes() == b"fake downloaded image"


def test_resolve_asset_not_found(tmp_path):
    """Test that resolve_asset raises FileNotFoundError when asset doesn't exist anywhere."""
    from panoconfig360_backend.render.vips_compat import resolve_asset
    
    # Mock requests.get to simulate 404
    mock_response = Mock()
    mock_response.status_code = 404
    
    test_base = tmp_path / "panoconfig360_cache" / "nonexistent"
    
    with patch("panoconfig360_backend.render.vips_compat.requests.get", return_value=mock_response):
        with pytest.raises(FileNotFoundError):
            resolve_asset(test_base)


def test_resolve_asset_url_construction():
    """Test that remote URLs are constructed correctly."""
    from panoconfig360_backend.render.vips_compat import construct_r2_url
    from pathlib import Path
    from unittest.mock import patch
    
    # Test URL construction with a specific R2_PUBLIC_URL
    test_url = "https://test.r2.dev"
    
    with patch("panoconfig360_backend.render.vips_compat.R2_PUBLIC_URL", test_url):
        base_path = Path("panoconfig360_cache/clients/monte-negro/scenes/kitchen/base_kitchen")
        remote_url = construct_r2_url(base_path, ".jpg")
        
        expected_url = f"{test_url}/clients/monte-negro/scenes/kitchen/base_kitchen.jpg"
        assert remote_url == expected_url

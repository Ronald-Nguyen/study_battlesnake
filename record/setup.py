from setuptools import setup, find_packages

setup(
    name="gum",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        # Core dependencies
        "pillow",  # For image processing
        "mss",  # For screen capture
        "pynput",  # For mouse/keyboard monitoring
        "shapely",  # For geometry operations
        "openai>=1.0.0",
        "SQLAlchemy>=2.0.0",
        "pydantic>=2.0.0",
        "sqlalchemy-utils>=0.41.0",
        "python-dotenv>=1.0.0",
        "scikit-learn",
        "aiosqlite",
        "greenlet",
        "requests",  # For GCS uploads
        "flask",  # For recording review web viewer
        "PyYAML",  # For Google Drive settings configuration
        "PyDrive",  # For Google Drive integration
        # Google Drive API dependencies (optional, for advanced features)
        "google-auth",  # For Google Drive API authentication
        "google-auth-oauthlib",  # For OAuth flow
        "google-auth-httplib2",  # For HTTP requests
        "google-api-python-client",  # For Google Drive API
    ],
    extras_require={
        "macos": [
            "pyobjc-framework-Quartz",
            "pyobjc-framework-Cocoa",
        ],
        "windows": [
            "pywin32",
            "psutil",
            "uiautomation; platform_system=='Windows'",
        ],
        "linux": [
            "python-xlib",
            "ewmh",
            "PyGObject",
            "dbus-python",  # For Portal integration on Wayland
        ],
        "monitoring": [
            "psutil",  # For memory monitoring
        ],
        "dev": ["pytest", "pytest-asyncio"],
    },
    entry_points={
        "console_scripts": [
            "gum=gum.cli:main",
        ],
    },
    description="A Python package with command-line interface",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)

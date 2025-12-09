from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="winsentry",
    version="1.1.0",
    author="WinSentry",
    description="Windows Service and Port Monitoring Tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "tornado>=6.0",
        "psutil>=5.8.0",
        "aiofiles>=0.8.0",
        "pywin32>=227",
        "WMI>=1.5.1",
    ],
    entry_points={
        "console_scripts": [
            "winsentry=winsentry.main:main",
        ],
    },
    scripts=[
        "run_winsentry.py",
    ],
    include_package_data=True,
    package_data={
        "winsentry": ["templates/*.html", "static/*"],
    },
)

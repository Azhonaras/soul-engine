from setuptools import setup, find_packages

setup(
    name="soul-engine",
    version="0.4.0",
    description="Epistemic Bio-Homeostatic Identity & Memory Kernel for AI Agents with Model Context Protocol (MCP) Interface",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="NBada",
    packages=find_packages(),
    py_modules=["soul_kernel", "soul_mcp_server", "install"],
    install_requires=[
        "numpy>=1.22.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "ruff>=0.1.0",
            "mypy>=1.0.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "soul-mcp=soul_mcp_server:main",
            "soul-install=install:main",
        ],
    },
    python_requires=">=3.9",
)

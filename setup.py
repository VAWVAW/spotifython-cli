import setuptools

with open("README.rst", "r", encoding="utf-8") as f:
    readme = f.read()

setuptools.setup(
    name="spotifython-cli",
    version="0.3.4",
    author="VAWVAW",
    author_email="vawvaw@vaw-valentin.de",
    description="A command line interface for spotifython intended for use with spotifyd",
    long_description=readme,
    long_description_content_type="text/x-rst",
    url="https://github.com/vawvaw/spotifython-cli",
    project_urls={
        "Bug Tracker": "https://github.com/vawvaw/spotifython-cli/issues",
        # "Documentation": "https://spotifython-cli.readthedocs.io/",
    },
    license="GPLv3",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Topic :: Internet",
        "Topic :: Utilities",
        "Typing :: Typed",
    ],
    py_modules=["spotifython_cli"],
    install_requires=["spotifython>=0.2.9", "click"],
    python_requires=">=3.10",
    entry_points={"console_scripts": ["spotifython-cli=spotifython_cli:cli"]},
)

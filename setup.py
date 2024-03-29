#! /usr/bin/env python

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()


setuptools.setup(
    name="code-librarian",
    version="0.1",
    entry_points = {
        'console_scripts': ['librarian=code_librarian.librarian:main'],
    },
    author="David Briscoe",
    #~ author_email="idbrii@users.noreply.github.com",
    description="Copy dependencies into your project, apply updates, and extract fixes.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/idbrii/librarian",
    package_dir={"": "src"},
    packages=setuptools.find_packages("src"),
    install_requires=["GitPython>=3.1.18"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)

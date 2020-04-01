import setuptools

with open("README.md", "r") as readme:
    long_description = readme.read()

setuptools.setup(
    name="pretty_j1939",
    version="0.0.2",
    author='"Ben Gardiner <ben.gardiner@nmfta.org>", "Jeremy Daily <jeremy.daily@colostate.edu>", Subhojeet Mukherjee <subhojeet.mukherjee@colostate.edu>',
    author_email='ben.gardiner@nmfta.org',
    description="python libs and scripts for pretty-printing J1939 logs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/nmfta-repo/pretty_j1939",
    packages=setuptools.find_packages(),
    install_requires=[
        'asteval',
        'defusedxml',
        'unidecode',
        'xlrd',
        'bitstring',
    ],
    scripts=[
        'create_j1939db-json.py',
        'pretty_j1939.py',
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)

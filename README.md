# Librarian

Librarian automates copying modules to and from projects

Librarian maintains a central Library for your modules. It copies modules
from the Library to your project and you can specify which kinds of files
you want included so you can skip demos/examples and tests. Librarian can
copy modules back to the Library from your project so you can contribute
them upstream or use them in other projects.

Librarian is an alternative to git submodules. Instead of putting creating
your own forks of git repos, granting access to your developers, and adding
submodules to your project, you can use librarian to clone the remote, copy
the files into your project, and copy changes back into your clone.

# Example

Create a 'love' config in librarian for lua projects that renames single
file libraries so they exist in a folder, but can still be imported by
name:

    librarian config love --path src/lib/ --root-marker init.lua --rename-single-file-root-marker ".*.lua" --include-pattern ".*.lua|LICENSE.*"

Register a 'love' module 'windfield':

    librarian acquire love windfield https://github.com/adnzzzzZ/windfield.git

Copy our 'love' module 'windfield' to a project 'puppypark':

    librarian checkout puppypark windfield

Copy changes in project 'puppypark' from module 'windfield' back to the Library:

    librarian checkin puppypark windfield

# License

MIT

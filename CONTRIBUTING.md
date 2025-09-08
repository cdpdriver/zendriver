# Contributing to Zendriver

First off, thanks for taking the time to contribute! ❤️

All types of contributions are encouraged and valued. See the [Table of Contents](#table-of-contents) for different ways to help and details about how this project handles them. Please make sure to read the relevant section before making your contribution. It will make it a lot easier for us maintainers and smooth out the experience for all involved. The community looks forward to your contributions. 🎉

> And if you like the project, but just don't have time to contribute, that's fine. There are other easy ways to support the project and show your appreciation, which we would also be very happy about:
>
> - Star the project
> - Tweet about it
> - Refer this project in your project's readme
> - Mention the project at local meetups and tell your friends/colleagues

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [I Have a Question](#i-have-a-question)
- [I Want To Contribute](#i-want-to-contribute)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Enhancements](#suggesting-enhancements)
- [Your First Code Contribution](#your-first-code-contribution)
- [Improving The Documentation](#improving-the-documentation)
- [Styleguides](#styleguides)
- [Code formatting and linting](#code-formatting-and-linting)

## Code of Conduct

This project and everyone participating in it is governed by a [Code of Conduct](https://github.com/cdpdriver/.github/blob/main/CODE_OF_CONDUCT.md).
By participating, you are expected to uphold this code. Please report unacceptable behavior to [oss@slensky.com](mailto:oss@slensky.com).

## I Have a Question

> If you want to ask a question, we assume that you have read the available [Documentation](https://zendriver.dev/).

Before you ask a question, it is best to search for existing [Issues](/issues) that might help you. In case you have found a suitable issue and still need clarification, you can write your question in this issue. It is also advisable to search the internet for answers first.

If you then still feel the need to ask a question and need clarification, we recommend the following:

- Open an [Issue](/issues/new).
- Provide as much context as you can about what you're running into.
- Provide project and platform versions (operating system, Chrome version, etc.), depending on what seems relevant.

We will then take care of the issue as soon as possible.

## I Want To Contribute

> ### Legal Notice
>
> When contributing to this project, you must agree that you have authored 100% of the content, that you have the necessary rights to the content and that the content you contribute may be provided under the project license.

### Reporting Bugs

#### Before Submitting a Bug Report

A good bug report shouldn't leave others needing to chase you up for more information. Therefore, we ask you to investigate carefully, collect information and describe the issue in detail in your report. Please complete the following steps in advance to help us fix any potential bug as fast as possible.

- Make sure that you are using the latest version.
- Determine if your bug is really a bug and not an error on your side e.g. using incompatible environment components/versions (Make sure that you have read the [documentation](https://zendriver.dev/). If you are looking for support, you might want to check [this section](#i-have-a-question)).
- To see if other users have experienced (and potentially already solved) the same issue you are having, check if there is not already a bug report existing for your bug or error in the [bug tracker](issues?q=label%3Abug).
- Also make sure to search the internet (including Stack Overflow) to see if users outside of the GitHub community have discussed the issue.
- Collect information about the bug:
- Stack trace (Traceback)
- OS, Platform and Package Version (Windows, Linux, macOS, x86, ARM)
- Python version
- Chrome version
- Can you reliably reproduce the issue? And can you also reproduce it with older versions?

#### How Do I Submit a Good Bug Report?

> You must never report security related issues, vulnerabilities or bugs including sensitive information to the issue tracker, or elsewhere in public. Instead sensitive bugs must be sent by email to [oss@slensky.com](mailto:oss@slensky.com).

We use GitHub issues to track bugs and errors. If you run into an issue with the project:

- Open an [Issue](/issues/new). (Since we can't be sure at this point whether it is a bug or not, we ask you not to talk about a bug yet and not to label the issue.)
- Explain the behavior you would expect and the actual behavior.
- Please provide as much context as possible and describe the _reproduction steps_ that someone else can follow to recreate the issue on their own. This usually includes your code. For good bug reports you should isolate the problem and create a reduced test case.
- Provide the information you collected in the previous section.

Once it's filed:

- The project team will label the issue accordingly.
- A team member will try to reproduce the issue with your provided steps. If there are no reproduction steps or no obvious way to reproduce the issue, the team will ask you for those steps and mark the issue as `needs-repro`. Bugs with the `needs-repro` tag will not be addressed until they are reproduced.
- If the team is able to reproduce the issue, it will be marked `needs-fix`, as well as possibly other tags (such as `critical`), and the issue will be left to be [implemented by someone](#your-first-code-contribution).

### Suggesting Enhancements

This section guides you through submitting an enhancement suggestion for Zendriver, **including completely new features and minor improvements to existing functionality**. Following these guidelines will help maintainers and the community to understand your suggestion and find related suggestions.

#### Before Submitting an Enhancement

- Make sure that you are using the latest version.
- Read the [documentation](https://zendriver.dev/) carefully and find out if the functionality is already covered, maybe by an individual configuration.
- Perform a [search](/issues) to see if the enhancement has already been suggested. If it has, add a comment to the existing issue instead of opening a new one.
- Find out whether your idea fits with the scope and aims of the project. It's up to you to make a strong case to convince the project's developers of the merits of this feature. Keep in mind that we want features that will be useful to the majority of our users and not just a small subset. If you're just targeting a minority of users, consider writing an add-on/plugin library.

#### How Do I Submit a Good Enhancement Suggestion?

Enhancement suggestions are tracked as [GitHub issues](/issues).

- Use a **clear and descriptive title** for the issue to identify the suggestion.
- Provide a **step-by-step description of the suggested enhancement** in as many details as possible.
- **Describe the current behavior** and **explain which behavior you expected to see instead** and why. At this point you can also tell which alternatives do not work for you.
- You may want to **include screenshots and animated GIFs** which help you demonstrate the steps or point out the part which the suggestion is related to. You can use [this tool](https://www.cockos.com/licecap/) to record GIFs on macOS and Windows, and [this tool](https://github.com/colinkeenan/silentcast) or [this tool](https://github.com/GNOME/byzanz) on Linux.
- **Explain why this enhancement would be useful** to most Zendriver users. You may also want to point out the other projects that solved it better and which could serve as inspiration.

### Your First Code Contribution

First, thank you! It's fantastic that you are interested in taking the step to become a code contributor. We welcome almost all code contributions, but please bear in mind that if your change is out-of-scope for the project, it may not be merged. If you are unsure whether your idea is appropriate, please first create a GitHub issue (see [Suggesting Enhancements](#suggesting-enhancements)) so that we can discuss it.

If this is your first time making a contribution on GitHub, please review the [official documentation](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request-from-a-fork) for familiarize yourself with the pull request process.

When submitting a pull request, please stick to the following guidelines:

1. Describe your change in the body of your pull request, ideally linking to an existing GitHub issue for the bug/enhancement you are addressing. Note, if you use the word "closes", "fixes", or "resolves" before linking your issue, the issue will be automatically closed when the pull request is merged (see [GitHub docs](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue#linking-a-pull-request-to-an-issue-using-a-keyword)).
2. Ensure that any newly added/modified code is autoformatted and free of lint errors. To verify this, use the [`scripts/lint.sh`](scripts/lint.sh) script to run `ruff` and `mypy` against your code.
3. Ensure that all tests pass: `uv run pytest`.
4. Get credit for your work! Add your changes to [`CHANGELOG.md`](CHANGELOG.md) under the `[UNRELEASED]` section and optionally include your GitHub handle at the end of the line.

> [!TIP]
> Here's an example of how you can format your entry in the changelog. Add the entry in whichever category is most appropriate. If there are any existing entries in the category, just place it after the last entry in that category.
>
> ```markdown
> ## [Unreleased]
>
> ### Fixed
>
> - Fixed a bug with caused the browser to crash @yourgithubhandle
>
> ### Added
>
> ### Changed
>
> ### Removed
> ```

### Improving The Documentation

Documentation improvements are always welcome! If you are interested in improving the documentation, please submit an enhancement issue (see [Suggesting Enhancements](#suggesting-enhancements)) so that we can discuss the best place to put it.

After you get in touch, feel free to submit a pull request just like you would for a code contribution (see [Your First Code Contribution](#your-first-code-contribution)).

## Styleguides

### Code formatting and linting

This repository is formatted and linted with [`ruff`](https://docs.astral.sh/ruff/) and type-checked with [`mypy`](https://mypy-lang.org/). All contributions should be 100% error-free in order to be merged.

For convenience, `ruff` and `mypy` can be run against the entire codebase with the [`scripts/lint.sh`](scripts/lint.sh) helper script.

## Attribution

This guide is based on the **contributing.md**. [Make your own](https://contributing.md/)!

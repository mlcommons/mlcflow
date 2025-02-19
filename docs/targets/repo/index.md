# Repo

Currently, the following actions are supported for repos:

## Add

`add` action is used to create a new MLC repo and register in MLCFlow. The newly created repo folder would be present inside the `repos` folder present inside the parent `MLC` folder.

**Syntax**

```bash
mlc add repo <repo_name/github_link>
```

Examples of `add` action for `repo` target could be found inside the GitHub action workflow [here](https://github.com/mlcommons/mlcflow/blob/d0269b47021d709e0ffa7fe0db8c79635bfd9dff/.github/workflows/test-mlc-core-actions.yaml).

## Find

`find` action is used to get the path of a particular repository registered in MLCFlow. 

**Syntax**

```bash
mlc find repo <repo_owner@repo_name>
```

OR

```bash
mlc find repo <repo_url>
```

OR

```bash
mlc find repo <repo_uid>
```

OR

```bash
mlc find repo <repo_alias>
```

OR

```bash
mlc find repo <repo_alias>,<repo_uid>
```

Examples of `find` action for `repo` target could be found inside the GitHub action workflow [here](https://github.com/mlcommons/mlcflow/blob/d0269b47021d709e0ffa7fe0db8c79635bfd9dff/.github/workflows/test-mlc-core-actions.yaml).

## Pull

`pull` action is used to clone a MLC repo and register in MLC.

**Syntax**

```bash
mlc pull repo <repo_owner>@<repo_name>
```

OR

```bash
mlc pull repo <repo_urll>
```

- The `--checkout` flag can be used if a user needs to check out a specific commit after cloning. The user must provide the commit SHA.
- The `--branch` flag can be used if a user needs to check out a specific branch after cloning. The user must provide the branch name.

Examples of `pull` action for `repo` target could be found inside the GitHub action workflow [here](https://github.com/mlcommons/mlcflow/blob/d0269b47021d709e0ffa7fe0db8c79635bfd9dff/.github/workflows/test-mlc-core-actions.yaml).

## List

`list` action is used to list the alias and path of the MLC repos registered in MLC.

**Syntax**

```bash
mlc list repo
```
Example of `list` action for `repo` target could be found inside the GitHub action workflow [here](https://github.com/mlcommons/mlcflow/blob/d0269b47021d709e0ffa7fe0db8c79635bfd9dff/.github/workflows/test-mlc-core-actions.yaml).

## Rm (Remove)

`rm` action is used to remove the specified repo registered in MLC.

**Syntax**

```bash
mlc rm repo <repo_owner>@<repo_name>
```
An example of the `rm` action for the `repo` target can be found in the GitHub Actions workflow [here](https://github.com/mlcommons/mlcflow/blob/d0269b47021d709e0ffa7fe0db8c79635bfd9dff/.github/workflows/test-mlc-core-actions.yaml).


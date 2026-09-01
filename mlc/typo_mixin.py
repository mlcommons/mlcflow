"""TypoMixin: argparse error mixin that suggests near-matches on invalid choice errors.

When a user types an unrecognised action or target, argparse normally exits
with a bare "invalid choice" message.  TypoMixin intercepts that error and
inserts a "Did you mean …?" hint before the standard error line, using
difflib.get_close_matches (stdlib, no extra dependencies).

Usage::

    class TypoArgumentParser(TypoMixin, argparse.ArgumentParser):
        pass

    parser = TypoArgumentParser(prog="mlc", ...)
    # Subparsers created from this parser inherit the class automatically
    # because argparse uses type(self) as the default parser_class.
"""

import difflib
import re
import sys


class TypoMixin:
    """Mixin for argparse.ArgumentParser that adds 'Did you mean?' suggestions.

    Drop this mixin to the left of argparse.ArgumentParser in your class MRO.
    It overrides only error() — no other behaviour changes.

    Attributes
    ----------
    _TYPO_CUTOFF : float
        Minimum SequenceMatcher similarity ratio (0–1) for a candidate to be
        shown.  Defaults to 0.6 (same as difflib.get_close_matches default).
    _TYPO_MAX_SUGGESTIONS : int
        Maximum number of alternatives displayed.
    """

    _TYPO_CUTOFF: float = 0.6
    _TYPO_MAX_SUGGESTIONS: int = 3

    # Matches argparse's invalid-choice message in Python 3.8 – 3.14:
    #   "invalid choice: 'rune' (choose from 'run', 'pull', 'test')"
    # The value is repr()'d so it's surrounded by single quotes.
    _INVALID_CHOICE_RE = re.compile(
        r"invalid choice: '?([^'()\s]+)'? \(choose from ([^)]+)\)"
    )

    # ------------------------------------------------------------------ #
    # Public helpers (tested directly)                                     #
    # ------------------------------------------------------------------ #

    def suggest(self, word: str, candidates) -> list:
        """Return the closest matches for *word* from *candidates*.

        Thin wrapper around difflib.get_close_matches so callers and tests
        can access the suggestion logic without triggering sys.exit.

        Parameters
        ----------
        word:
            The mistyped string entered by the user.
        candidates:
            Iterable of valid strings to compare against.

        Returns
        -------
        list[str]
            Up to _TYPO_MAX_SUGGESTIONS matches ordered by similarity,
            or an empty list when no match exceeds _TYPO_CUTOFF.
        """
        return difflib.get_close_matches(
            word,
            candidates,
            n=self._TYPO_MAX_SUGGESTIONS,
            cutoff=self._TYPO_CUTOFF,
        )

    # ------------------------------------------------------------------ #
    # argparse.ArgumentParser override                                     #
    # ------------------------------------------------------------------ #

    def error(self, message: str) -> None:
        """Print usage, an optional 'Did you mean?' hint, then the standard error.

        The output order mirrors standard argparse except for the hint line
        injected between the usage block and the error message:

            usage: mlc [-h] {run,pull,...} ...

            Did you mean 'run'?

            mlc: error: argument command: invalid choice: 'rune' (…)
        """
        self.print_usage(sys.stderr)

        m = self._INVALID_CHOICE_RE.search(message)
        if m:
            invalid = m.group(1)
            # Choices are repr()'d in the error text: "'run', 'pull', ..."
            raw_choices = [c.strip().strip("'\"") for c in m.group(2).split(",")]
            suggestions = self.suggest(invalid, raw_choices)
            if suggestions:
                if len(suggestions) == 1:
                    hint = f"Did you mean '{suggestions[0]}'?"
                else:
                    quoted = ", ".join(f"'{s}'" for s in suggestions)
                    hint = f"Did you mean one of: {quoted}?"
                sys.stderr.write(f"\n{hint}\n\n")

        args = {"prog": self.prog, "message": message}
        self.exit(2, "%(prog)s: error: %(message)s\n" % args)

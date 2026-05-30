# cli/retro_ui.py

## Purpose

Renders the CHOICE-inspired retro terminal UI used by the CLI.
Handles low-level screen control, box-drawing layout, and text styling.

## Key functions

- `clear_screen() -> None`
- `move_cursor(x: int = 0, y: int = 0) -> None`
- `hide_cursor() -> None`
- `show_cursor() -> None`

- `render_header(title: str, subtitle: str = "") -> None`
- `render_menu(items: Sequence[str], selected: int = 0, group_labels: list[str] | None = None) -> None`
- `render_state(state_lines: list[str]) -> None`
- `render_shortcut_bar(shortcuts: list[tuple[str, str]]) -> None`
- `render_separator() -> None`
- `render_status_bar(message: str, shortcuts: list[tuple[str, str]] | None = None) -> None`

- `prompt_input(prompt_text: str, default: str = "") -> str`

## Internal helpers

- `_green(text: str, bright: bool = False) -> str`
- `_dim(text: str) -> str`
- `_bold(text: str) -> str`
- `_inverse(text: str) -> str`
- `_visible_len(text: str) -> int`
- `_terminal_width() -> int`
- `_effective_width() -> int`

## Notes

- Uses ANSI escape codes and only applies them when stdout is a TTY.
- Supports safe output when terminal size cannot be determined.
- Provides a retro green-on-black interface for the CLI.

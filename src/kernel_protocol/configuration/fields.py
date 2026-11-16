from kernel_protocol.configuration.errors import (
    MISSING_KEY,
    OUT_OF_RANGE,
    UNKNOWN_KEY,
    WRONG_TYPE,
    ConfigurationError,
)


class Section:
    def __init__(self, name: str, values: dict[str, object]) -> None:
        self.name = name
        self._values = values
        self._read: list[str] = []

    def has(self, key: str) -> bool:
        return key in self._values

    def number(self, key: str, lowest: int, highest: int) -> int:
        value = self._take(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigurationError(WRONG_TYPE, self._where(key))
        if value < lowest or value > highest:
            raise ConfigurationError(OUT_OF_RANGE, self._where(key))
        return value

    def number_or(self, key: str, lowest: int, highest: int, default: int) -> int:
        if key not in self._values:
            return default
        return self.number(key, lowest, highest)

    def text(self, key: str) -> str:
        value = self._take(key)
        if not isinstance(value, str):
            raise ConfigurationError(WRONG_TYPE, self._where(key))
        return value

    def text_or(self, key: str, default: str) -> str:
        if key not in self._values:
            return default
        return self.text(key)

    def texts_or_none(self, key: str) -> list[str]:
        if key not in self._values:
            return []
        value = self._take(key)
        if not isinstance(value, list):
            raise ConfigurationError(WRONG_TYPE, self._where(key))
        texts = []
        for item in value:
            if not isinstance(item, str):
                raise ConfigurationError(WRONG_TYPE, self._where(key))
            if item in texts:
                raise ConfigurationError(OUT_OF_RANGE, self._where(key))
            texts.append(item)
        return texts

    def finish(self) -> None:
        for key in sorted(self._values):
            if key not in self._read:
                raise ConfigurationError(UNKNOWN_KEY, self._where(key))

    def _take(self, key: str) -> object:
        if key not in self._values:
            raise ConfigurationError(MISSING_KEY, self._where(key))
        self._read.append(key)
        return self._values[key]

    def _where(self, key: str) -> str:
        return f"{self.name}.{key}"

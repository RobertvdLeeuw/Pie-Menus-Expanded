from attrs import define


@define
class MenuOption:
    label: str
    function: str  # TODO: add function name parser/checker
    params: dict | list

    enabled: bool = True

    triggerKey: str = None
    icon: str = None

    subslices: list[type] = None  # List of MenuOptions

    def toDict(self) -> dict:
        data = {'label': self.label,
                'function': self.function,
                'params': self.params,
                'enabled': self.enabled}

        if self.triggerKey:
            data['triggerKey'] = self.triggerKey

        if self.icon:
            data['icon'] = self.icon

        return data

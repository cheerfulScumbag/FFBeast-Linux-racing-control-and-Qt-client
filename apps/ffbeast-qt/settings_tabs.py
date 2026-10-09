from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    field_id: int
    size: int
    minimum: int
    maximum: int
    section: str
    widget: str = "spin"
    signed: bool = False
    index: int = 0
    step: int = 1
    choices: tuple[tuple[str, int], ...] = ()


def _encode_value(value: int, size: int, signed: bool) -> list[int]:
    return list(int(value).to_bytes(size, byteorder="little", signed=signed))


class SliderField(QWidget):
    value_changed = Signal(int)

    def __init__(self, minimum: int, maximum: int, step: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._slider = QSlider(Qt.Orientation.Horizontal, self)
        self._slider.setRange(minimum, maximum)
        self._slider.setSingleStep(step)
        self._slider.setPageStep(max(step, (maximum - minimum) // 10 or 1))

        self._spin = QSpinBox(self)
        self._spin.setRange(minimum, maximum)
        self._spin.setSingleStep(step)
        self._spin.setFixedWidth(92)

        self._slider.valueChanged.connect(self._spin.setValue)
        self._spin.valueChanged.connect(self._slider.setValue)
        self._spin.valueChanged.connect(self.value_changed.emit)

        layout.addWidget(self._slider, 1)
        layout.addWidget(self._spin)

    def set_value(self, value: int) -> None:
        self._spin.setValue(value)

    def value(self) -> int:
        return self._spin.value()


class ToggleField(QCheckBox):
    def set_value(self, value: int) -> None:
        self.setChecked(bool(value))

    def value(self) -> int:
        return 1 if self.isChecked() else 0


class ComboField(QComboBox):
    def __init__(self, choices: tuple[tuple[str, int], ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        for label, value in choices:
            self.addItem(label, value)

    def set_value(self, value: int) -> None:
        index = self.findData(value)
        if index >= 0:
            self.setCurrentIndex(index)

    def value(self) -> int:
        data = self.currentData()
        return int(data) if data is not None else 0


class SpinField(QSpinBox):
    def set_value(self, value: int) -> None:
        self.setValue(value)

    def value(self) -> int:
        return super().value()


class SettingsPage(QWidget):
    apply_requested = Signal(str, list)

    def __init__(
        self,
        page_name: str,
        title: str,
        description: str,
        specs: list[FieldSpec],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._page_name = page_name
        self._specs = specs
        self._widgets: dict[str, QWidget] = {}
        self._build_ui(title, description)

    def _build_ui(self, title: str, description: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        header = QLabel(title, self)
        header.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(header)

        summary = QLabel(description, self)
        summary.setWordWrap(True)
        summary.setStyleSheet("color: #5b6470;")
        layout.addWidget(summary)

        # Create a horizontal layout to act as our two columns
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(16)
        
        left_column = QVBoxLayout()
        right_column = QVBoxLayout()

        sections: dict[str, list[FieldSpec]] = {}
        for spec in self._specs:
            sections.setdefault(spec.section, []).append(spec)

        # Alternately distribute the settings groups into left and right tracks
        for i, (section_name, section_specs) in enumerate(sections.items()):
            group = QGroupBox(section_name, self)
            group_layout = QFormLayout(group)
            group_layout.setHorizontalSpacing(18)
            group_layout.setVerticalSpacing(10)

            for spec in section_specs:
                widget = self._create_widget(spec, group)
                self._widgets[spec.key] = widget
                group_layout.addRow(spec.label, widget)

            if i % 2 == 0:
                left_column.addWidget(group)
            else:
                right_column.addWidget(group)

        # Force all widgets to anchor tightly to the top of their track
        left_column.addStretch(1)
        right_column.addStretch(1)

        # Nest the columns back into the main layout flow
        columns_layout.addLayout(left_column, 1)
        columns_layout.addLayout(right_column, 1)
        layout.addLayout(columns_layout)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        apply_button = QPushButton("Apply Page Changes", self)
        apply_button.clicked.connect(self._emit_updates)
        button_row.addWidget(apply_button)
        layout.addLayout(button_row)

    def _create_widget(self, spec: FieldSpec, parent: QWidget) -> QWidget:
        if spec.widget == "slider":
            return SliderField(spec.minimum, spec.maximum, spec.step, parent)

        if spec.widget == "toggle":
            return ToggleField(parent)

        if spec.widget == "combo":
            return ComboField(spec.choices, parent)

        widget = SpinField(parent)
        widget.setMinimum(spec.minimum)
        widget.setMaximum(spec.maximum)
        widget.setSingleStep(spec.step)
        if spec.signed:
            widget.setRange(spec.minimum, spec.maximum)
        return widget

    def set_values(self, values: dict[str, int]) -> None:
        for spec in self._specs:
            value = values.get(spec.key)
            if value is None:
                continue
            if isinstance(value, bool):
                value = int(value)
            if isinstance(value, int):
                widget = self._widgets[spec.key]
                widget.set_value(value)  # type: ignore[attr-defined]

    def values(self) -> dict[str, int]:
        output: dict[str, int] = {}
        for spec in self._specs:
            widget = self._widgets[spec.key]
            output[spec.key] = int(widget.value())  # type: ignore[attr-defined]
        return output

    def collect_updates(self) -> list[dict]:
        updates = []
        for spec in self._specs:
            widget = self._widgets[spec.key]
            value = int(widget.value())  # type: ignore[attr-defined]
            data = _encode_value(value, spec.size, spec.signed)
            updates.append(
                {
                    "name": spec.key,
                    "payload": {
                        "UpdateHardwareField": {
                            "field_id": spec.field_id,
                            "index": spec.index,
                            "data": data,
                        }
                    },
                }
            )
        return updates

    def _emit_updates(self) -> None:
        self.apply_requested.emit(self._page_name, self.collect_updates())


class ProfilesPage(QWidget):
    save_requested = Signal()
    load_requested = Signal()
    apply_requested = Signal()

    def __init__(self, profile_selector: QComboBox, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile_selector = profile_selector
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        header = QLabel("Profiles", self)
        header.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(header)

        description = QLabel(
            "Save and reapply sim-specific wheel setups. Profiles store drive and wheel setup values only.",
            self,
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #5b6470;")
        layout.addWidget(description)

        group = QGroupBox("Game Profiles", self)
        group_layout = QGridLayout(group)
        group_layout.addWidget(QLabel("Profile"), 0, 0)
        group_layout.addWidget(self.profile_selector, 0, 1, 1, 3)

        save_button = QPushButton("Save Current Setup", group)
        load_button = QPushButton("Load Into UI", group)
        apply_button = QPushButton("Apply To Wheel", group)

        save_button.clicked.connect(self.save_requested.emit)
        load_button.clicked.connect(self.load_requested.emit)
        apply_button.clicked.connect(self.apply_requested.emit)

        group_layout.addWidget(save_button, 1, 1)
        group_layout.addWidget(load_button, 1, 2)
        group_layout.addWidget(apply_button, 1, 3)
        layout.addWidget(group)
        layout.addStretch(1)


class MaintenancePage(QWidget):
    def __init__(
        self,
        save_button: QPushButton,
        reset_button: QPushButton,
        reboot_button: QPushButton,
        dfu_button: QPushButton,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._build_ui(save_button, reset_button, reboot_button, dfu_button)

    def _build_ui(
        self,
        save_button: QPushButton,
        reset_button: QPushButton,
        reboot_button: QPushButton,
        dfu_button: QPushButton,
    ) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        header = QLabel("Maintenance", self)
        header.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(header)

        description = QLabel(
            "Use these actions for wheel maintenance and recovery. DFU should only be used when you intend to flash firmware.",
            self,
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #5b6470;")
        layout.addWidget(description)

        group = QGroupBox("Device Actions", self)
        group_layout = QVBoxLayout(group)
        for button in (save_button, reset_button, reboot_button, dfu_button):
            button.setMinimumHeight(36)
            group_layout.addWidget(button)
        layout.addWidget(group)
        layout.addStretch(1)


DRIVE_SPECS = [
    FieldSpec("motion_range", "Motion Range", 5, 2, 90, 3600, "Steering", "slider", step=10),
    FieldSpec("total_effect_strength", "Total Strength", 4, 1, 0, 255, "Force Feedback", "slider"),
    FieldSpec("soft_stop_strength", "Soft Stop Strength", 6, 1, 0, 255, "Force Feedback", "slider"),
    FieldSpec("soft_stop_range", "Soft Stop Range", 7, 1, 0, 255, "Force Feedback", "slider"),
    FieldSpec(
        "soft_stop_dampening_strength",
        "Soft Stop Dampening",
        9,
        2,
        0,
        65535,
        "Force Feedback",
        "slider",
        step=128,
    ),
    FieldSpec(
        "static_dampening_strength",
        "Static Dampening",
        8,
        2,
        0,
        65535,
        "Dampening",
        "slider",
        step=128,
    ),
    FieldSpec(
        "dynamic_dampening_strength",
        "Dynamic Dampening",
        10,
        2,
        0,
        65535,
        "Dampening",
        "slider",
        step=128,
    ),
]

WHEEL_SETUP_SPECS = [
    FieldSpec("force_enabled", "Enable Force Feedback", 11, 1, 0, 1, "Core Controls", "toggle"),
    FieldSpec(
        "force_direction",
        "Force Output Direction",
        22,
        1,
        -1,
        1,
        "Core Controls",
        "combo",
        True,
        choices=(("Normal", 1), ("Inverted", -1)),
    ),
    FieldSpec(
        "encoder_direction",
        "Joystick Output Direction",
        21,
        1,
        -1,
        1,
        "Core Controls",
        "combo",
        True,
        choices=(("Normal", 1), ("Inverted", -1)),
    ),
    FieldSpec("power_limit", "Power Limit", 17, 1, 0, 255, "Motor Limits", "slider"),
    FieldSpec("braking_limit", "Braking Resistor Limit", 18, 1, 0, 255, "Motor Limits", "slider"),
    FieldSpec("encoder_cpr", "Encoder CPR", 24, 2, 0, 65535, "Motor Setup", "spin", step=64),
    FieldSpec("pole_pairs", "Pole Pairs", 23, 1, 0, 255, "Motor Setup", "spin"),
]

ADVANCED_WHEEL_SPECS = [
    FieldSpec(
        "calibration_magnitude",
        "Calibration Magnitude",
        15,
        1,
        0,
        255,
        "Calibration",
        "slider",
    ),
    FieldSpec("calibration_speed", "Calibration Speed", 16, 1, 0, 255, "Calibration", "slider"),
    FieldSpec(
        "position_smoothing",
        "Position Smoothing",
        19,
        1,
        0,
        255,
        "Filtering",
        "slider",
    ),
    FieldSpec("speed_buffer_size", "Speed Sample Buffer", 20, 1, 0, 255, "Filtering", "slider"),
    FieldSpec("proportional_gain", "P Gain", 25, 1, 0, 255, "Control Loop", "spin"),
    FieldSpec("integral_gain", "I Gain", 26, 2, 0, 65535, "Control Loop", "spin"),
    FieldSpec("debug_torque", "Debug Force", 12, 1, 0, 1, "Control Loop", "toggle"),
]

GPIO_SPECS = [
    FieldSpec(
        "extension_mode",
        "Extension Mode",
        27,
        1,
        0,
        255,
        "Peripheral Bus",
        "combo",
        choices=(("Disabled", 0), ("GPIO", 1), ("SPI", 2)),
    ),
    FieldSpec(
        "spi_mode",
        "SPI Mode",
        30,
        1,
        0,
        255,
        "Peripheral Bus",
        "combo",
        choices=(("Mode 0", 0), ("Mode 1", 1), ("Mode 2", 2), ("Mode 3", 3)),
    ),
    FieldSpec(
        "spi_latch_mode",
        "SPI Latch Mode",
        31,
        1,
        0,
        255,
        "Peripheral Bus",
        "combo",
        choices=(("Disabled", 0), ("Leading Edge", 1), ("Trailing Edge", 2)),
    ),
    FieldSpec("spi_latch_delay", "SPI Latch Delay", 32, 1, 0, 255, "Peripheral Timing", "spin"),
    FieldSpec(
        "spi_clk_pulse_length",
        "SPI Clock Pulse Length",
        33,
        1,
        0,
        255,
        "Peripheral Timing",
        "spin",
    ),
]

ADC_SPECS = [
    FieldSpec("raxis_min_0", "Axis 1 Min", 34, 2, 0, 65535, "Axis Range", "slider", index=0, step=32),
    FieldSpec("raxis_min_1", "Axis 2 Min", 34, 2, 0, 65535, "Axis Range", "slider", index=1, step=32),
    FieldSpec("raxis_min_2", "Axis 3 Min", 34, 2, 0, 65535, "Axis Range", "slider", index=2, step=32),
    FieldSpec("raxis_max_0", "Axis 1 Max", 35, 2, 0, 65535, "Axis Range", "slider", index=0, step=32),
    FieldSpec("raxis_max_1", "Axis 2 Max", 35, 2, 0, 65535, "Axis Range", "slider", index=1, step=32),
    FieldSpec("raxis_max_2", "Axis 3 Max", 35, 2, 0, 65535, "Axis Range", "slider", index=2, step=32),
    FieldSpec(
        "raxis_to_button_low_0",
        "Axis 1 Button Low",
        36,
        1,
        0,
        255,
        "Button Thresholds",
        "slider",
        index=0,
    ),
    FieldSpec(
        "raxis_to_button_low_1",
        "Axis 2 Button Low",
        36,
        1,
        0,
        255,
        "Button Thresholds",
        "slider",
        index=1,
    ),
    FieldSpec(
        "raxis_to_button_low_2",
        "Axis 3 Button Low",
        36,
        1,
        0,
        255,
        "Button Thresholds",
        "slider",
        index=2,
    ),
    FieldSpec(
        "raxis_to_button_high_0",
        "Axis 1 Button High",
        37,
        1,
        0,
        255,
        "Button Thresholds",
        "slider",
        index=0,
    ),
    FieldSpec(
        "raxis_to_button_high_1",
        "Axis 2 Button High",
        37,
        1,
        0,
        255,
        "Button Thresholds",
        "slider",
        index=1,
    ),
    FieldSpec(
        "raxis_to_button_high_2",
        "Axis 3 Button High",
        37,
        1,
        0,
        255,
        "Button Thresholds",
        "slider",
        index=2,
    ),
    FieldSpec("raxis_smoothing_0", "Axis 1 Smoothing", 38, 1, 0, 255, "Axis Smoothing", "slider", index=0),
    FieldSpec("raxis_smoothing_1", "Axis 2 Smoothing", 38, 1, 0, 255, "Axis Smoothing", "slider", index=1),
    FieldSpec("raxis_smoothing_2", "Axis 3 Smoothing", 38, 1, 0, 255, "Axis Smoothing", "slider", index=2),
    FieldSpec("raxis_invert_0", "Axis 1 Invert", 39, 1, 0, 1, "Axis Direction", "toggle", index=0),
    FieldSpec("raxis_invert_1", "Axis 2 Invert", 39, 1, 0, 1, "Axis Direction", "toggle", index=1),
    FieldSpec("raxis_invert_2", "Axis 3 Invert", 39, 1, 0, 1, "Axis Direction", "toggle", index=2),
]

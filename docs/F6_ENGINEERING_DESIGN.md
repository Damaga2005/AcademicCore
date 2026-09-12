# F6 Engineering Foundation

The engineering model is a deterministic domain layer, not a simulator.
Quantities use Decimal values and SI-base dimension vectors. Equations are
parsed by an explicit recursive parser and evaluated only against typed
Quantity inputs. Circuits contain explicit components, pins and nets; the
netlist is canonical text for representation and future backends only.

F7 owns real simulation and external processes. F8 owns measurement,
uncertainty, instruments and GUM/Monte Carlo. F6 provides no subprocess
execution and no external runtime dependency.

"""Tests for Phase F7-B7 GUM / Measurement Uncertainty Evaluation Engine.

Covers ISO/IEC Guide 98-3 (GUM) implementation:
- Pure-Python Student's t distribution and incomplete beta function
- ISO Guide 98-3 Table G.2 exact benchmark validation
- Type A evaluations from observations (Bessel corrected s / sqrt(n), dof = n - 1)
- Type B evaluations (Rectangular, Triangular, Normal, Explicit)
- Sensitivity coefficients (Explicit, Analytic, Central Finite Difference)
- Correlation & Covariance matrix propagation
- Combined standard uncertainty u_c(y)
- Welch-Satterthwaite effective degrees of freedom (nu_eff) with finite and infinite dof
- Dynamic Student's t coverage factor k (strictly non-hardcoded)
- Expanded uncertainty U = k * u_c(y)
- Structured UncertaintyBudget table with deterministic sorting and serialization
- Analytical Validation Cases A through J:
    Case A: Sum (Y = X1 + X2)
    Case B: Product (Y = X1 * X2)
    Case C: Voltage Divider (Vout = Vin * R2 / (R1 + R2))
    Case D: Correlation (r = +1 and r = -1)
    Case E: Type A from observations
    Case F: Type B Rectangular (a / sqrt(3))
    Case G: Type B Triangular (a / sqrt(6))
    Case H: Type B Normal (U / k)
    Case I: Welch-Satterthwaite with finite degrees of freedom
    Case J: Small nu_eff producing k != 2
- End-to-end integration with EngineeringService and CAS FileBlobStore
"""

from __future__ import annotations

import math
from decimal import Decimal
import pytest

from academic_core.application.engineering import EngineeringService
from academic_core.domain.engineering.gum import (
    CorrelationMatrix,
    GUMResult,
    InputQuantity,
    MeasurementModel,
    SensitivityMethod,
    UncertaintyBudget,
    UncertaintyBudgetRow,
    UncertaintyDistribution,
    UncertaintyType,
    betacf,
    calculate_coverage_factor,
    evaluate_gum,
    ibeta,
    student_t_cdf,
    student_t_quantile,
    type_a_from_observations,
    type_b_normal,
    type_b_rectangular,
    type_b_triangular,
)
from academic_core.domain.engineering.units import CURRENT, LENGTH, Quantity, UnitError, parse_unit
from academic_core.infrastructure.cas import FileBlobStore
from academic_core.infrastructure.database import Database
from academic_core.infrastructure.engineering import EngineeringRepository


# ==============================================================================
# 1. Student's t Distribution & ISO/IEC Guide 98-3 Table G.2 Benchmarks
# ==============================================================================

class TestStudentTDistribution:
    """Validate Student-t CDF and quantile against ISO/IEC Guide 98-3 Table G.2."""

    def test_incomplete_beta_edge_cases(self):
        assert ibeta(1.0, 1.0, 0.0) == 0.0
        assert ibeta(1.0, 1.0, 1.0) == 1.0
        with pytest.raises(ValueError, match="out of bounds"):
            ibeta(1.0, 1.0, -0.1)
        with pytest.raises(ValueError, match="out of bounds"):
            ibeta(1.0, 1.0, 1.1)

    def test_table_g2_95_percent_coverage(self):
        """ISO Guide 98-3 Table G.2 values for p = 0.95 (two-tailed coverage)."""
        expected_table = {
            1: 12.71,
            2: 4.30,
            3: 3.18,
            4: 2.78,
            5: 2.57,
            6: 2.45,
            7: 2.36,
            8: 2.31,
            9: 2.26,
            10: 2.23,
            20: 2.09,
            50: 2.01,
            100: 1.98,
        }
        for nu, expected_k in expected_table.items():
            k = float(calculate_coverage_factor(0.95, float(nu)))
            assert abs(k - expected_k) <= 0.015, (
                f"nu={nu}: computed k={k:.4f}, expected {expected_k}"
            )

    def test_table_g2_99_percent_coverage(self):
        """ISO Guide 98-3 Table G.2 values for p = 0.99."""
        expected_table = {
            1: 63.66,
            2: 9.92,
            3: 5.84,
            4: 4.60,
            5: 4.03,
            10: 3.17,
        }
        for nu, expected_k in expected_table.items():
            k = float(calculate_coverage_factor(0.99, float(nu)))
            assert abs(k - expected_k) <= 0.02, (
                f"nu={nu}: computed k={k:.4f}, expected {expected_k}"
            )

    def test_infinite_degrees_of_freedom_standard_normal(self):
        """As nu -> inf, Student's t converges to standard normal."""
        # p = 0.6827 -> k = 1.000
        k_68 = float(calculate_coverage_factor(0.6827, math.inf))
        assert abs(k_68 - 1.000) < 0.005

        # p = 0.95 -> k = 1.960
        k_95 = float(calculate_coverage_factor(0.95, math.inf))
        assert abs(k_95 - 1.960) < 0.005

        # p = 0.9545 -> k = 2.000
        k_9545 = float(calculate_coverage_factor(0.9545, math.inf))
        assert abs(k_9545 - 2.000) < 0.005

        # p = 0.99 -> k = 2.576
        k_99 = float(calculate_coverage_factor(0.99, math.inf))
        assert abs(k_99 - 2.576) < 0.005

        # p = 0.9973 -> k = 3.000
        k_9973 = float(calculate_coverage_factor(0.9973, math.inf))
        assert abs(k_9973 - 3.000) < 0.005

    def test_invalid_coverage_parameters(self):
        with pytest.raises(ValueError, match="Coverage probability"):
            calculate_coverage_factor(0.0, 10)
        with pytest.raises(ValueError, match="Coverage probability"):
            calculate_coverage_factor(1.0, 10)
        with pytest.raises(ValueError, match="Degrees of freedom"):
            calculate_coverage_factor(0.95, 0)
        with pytest.raises(ValueError, match="Degrees of freedom"):
            calculate_coverage_factor(0.95, -5)


# ==============================================================================
# 2. Input Quantity Types and Distributions (Type A & Type B)
# ==============================================================================

class TestInputQuantities:
    """Validate Type A from sample observations and Type B distributions."""

    def test_type_a_from_observations(self):
        # Sample observations with known stats
        # Data: [10.0, 10.2, 10.1, 9.9, 10.3] -> n = 5
        # mean = 10.1
        # deviations: -0.1, +0.1, 0.0, -0.2, +0.2 -> sum of squares = 0.01 + 0.01 + 0 + 0.04 + 0.04 = 0.10
        # s^2 = 0.10 / 4 = 0.025
        # s = sqrt(0.025) = 0.15811388...
        # u = s / sqrt(5) = sqrt(0.005) = 0.070710678...
        data = [10.0, 10.2, 10.1, 9.9, 10.3]
        mean, u, nu = type_a_from_observations(data)
        assert abs(float(mean) - 10.1) < 1e-12
        assert abs(float(u) - math.sqrt(0.005)) < 1e-12
        assert nu == 4.0

        q = InputQuantity.from_observations("V1", data, unit="V")
        assert q.uncertainty_type == UncertaintyType.TYPE_A
        assert q.distribution == UncertaintyDistribution.STUDENT_T
        assert q.degrees_of_freedom == 4.0
        assert q.unit == "V"

    def test_type_a_requires_minimum_two_observations(self):
        with pytest.raises(ValueError, match="at least 2 observations"):
            type_a_from_observations([42.0])
        with pytest.raises(ValueError, match="at least 2 observations"):
            type_a_from_observations([])

    def test_type_b_rectangular(self):
        # Half-width a = 0.05 V -> u = 0.05 / sqrt(3) = 0.0288675 V
        u, nu = type_b_rectangular(0.05)
        expected = 0.05 / math.sqrt(3)
        assert abs(float(u) - expected) < 1e-12
        assert math.isinf(nu)

        q = InputQuantity.rectangular("R1", 1000.0, 10.0, unit="ohm")
        assert q.uncertainty_type == UncertaintyType.TYPE_B
        assert q.distribution == UncertaintyDistribution.RECTANGULAR
        assert math.isinf(q.degrees_of_freedom)
        assert abs(float(q.standard_uncertainty) - (10.0 / math.sqrt(3))) < 1e-10

        with pytest.raises(ValueError, match="Half-width.*must be non-negative"):
            type_b_rectangular(-1.0)

    def test_type_b_triangular(self):
        # Half-width a = 0.06 mm -> u = 0.06 / sqrt(6) = 0.0244949 mm
        u, nu = type_b_triangular(0.06)
        expected = 0.06 / math.sqrt(6)
        assert abs(float(u) - expected) < 1e-12
        assert math.isinf(nu)

        q = InputQuantity.triangular("L1", 100.0, 0.06, unit="mm")
        assert q.uncertainty_type == UncertaintyType.TYPE_B
        assert q.distribution == UncertaintyDistribution.TRIANGULAR
        assert abs(float(q.standard_uncertainty) - (0.06 / math.sqrt(6))) < 1e-10

        with pytest.raises(ValueError, match="Half-width.*must be non-negative"):
            type_b_triangular(-0.5)

    def test_type_b_normal(self):
        # Calibration certificate: expanded U = 0.1 V at k = 2.0 -> u = 0.05 V
        u, nu = type_b_normal(0.1, coverage_factor=2.0)
        assert abs(float(u) - 0.05) < 1e-12
        assert math.isinf(nu)

        # Finite degrees of freedom specified from calibration
        u2, nu2 = type_b_normal(0.1, coverage_factor=2.0, degrees_of_freedom=15.0)
        assert abs(float(u2) - 0.05) < 1e-12
        assert nu2 == 15.0

        q = InputQuantity.normal("V_cal", 10.0, expanded_uncertainty=0.1, k=2.0, unit="V")
        assert q.uncertainty_type == UncertaintyType.TYPE_B
        assert q.distribution == UncertaintyDistribution.NORMAL
        assert abs(float(q.standard_uncertainty) - 0.05) < 1e-12

        with pytest.raises(ValueError, match="Coverage factor.*must be strictly positive"):
            type_b_normal(0.1, coverage_factor=0.0)

    def test_input_quantity_validation(self):
        with pytest.raises(ValueError, match="Standard uncertainty must be non-negative"):
            InputQuantity(
                name="bad",
                nominal_value=1.0,
                standard_uncertainty=-0.1,
                unit="V",
            )
        with pytest.raises(ValueError, match="Degrees of freedom must be strictly positive"):
            InputQuantity(
                name="bad_dof",
                nominal_value=1.0,
                standard_uncertainty=0.1,
                degrees_of_freedom=0,
                unit="V",
            )


# ==============================================================================
# 3. Correlation Matrix and Covariance Propagation
# ==============================================================================

class TestCorrelationMatrix:
    """Validate correlation matrix symmetry, bounds, and covariance calculation."""

    def test_valid_correlations(self):
        corr = CorrelationMatrix()
        corr.set_correlation("X1", "X2", 0.5)
        assert corr.get_correlation("X1", "X2") == Decimal("0.5")
        assert corr.get_correlation("X2", "X1") == Decimal("0.5")
        assert corr.get_correlation("X1", "X1") == Decimal("1.0")
        assert corr.get_correlation("X1", "X3") == Decimal("0.0")

        # Covariance: r * u1 * u2
        cov = corr.get_covariance("X1", "X2", Decimal("0.1"), Decimal("0.2"))
        assert abs(float(cov) - 0.01) < 1e-12

    def test_correlation_bounds(self):
        corr = CorrelationMatrix()
        with pytest.raises(ValueError, match="Correlation coefficient.*out of range"):
            corr.set_correlation("X1", "X2", 1.05)
        with pytest.raises(ValueError, match="Correlation coefficient.*out of range"):
            corr.set_correlation("X1", "X2", -1.1)

    def test_from_dict_and_matrix(self):
        d = {("A", "B"): 0.4, ("B", "A"): 0.4}
        c = CorrelationMatrix.from_dict(d)
        assert c.get_correlation("A", "B") == Decimal("0.4")

        # Asymmetry raises error
        with pytest.raises(ValueError, match="Asymmetric correlation"):
            CorrelationMatrix.from_dict({("A", "B"): 0.4, ("B", "A"): 0.6})


# ==============================================================================
# 4. Analytical Validation Cases A through J (ISO/IEC Guide 98-3 Specification)
# ==============================================================================

class TestAnalyticalValidationCases:
    """Validation cases A through J as specified in the 14-page GUM spec."""

    def test_case_a_sum_independent(self):
        """Case A: Y = X1 + X2 (independent inputs).
        X1 = 10, u1 = 0.1
        X2 = 20, u2 = 0.2
        c1 = 1, c2 = 1
        u_c = sqrt(0.1^2 + 0.2^2) = sqrt(0.05) ~= 0.2236068
        """
        model = MeasurementModel(
            measurand="Y",
            equation="X1 + X2",
            input_names=("X1", "X2"),
            output_unit="V",
        )
        inputs = {
            "X1": InputQuantity.explicit("X1", 10.0, 0.1, unit="V"),
            "X2": InputQuantity.explicit("X2", 20.0, 0.2, unit="V"),
        }
        res = evaluate_gum(model, inputs)
        assert abs(float(res.measurand_value) - 30.0) < 1e-12
        assert abs(float(res.combined_standard_uncertainty) - math.sqrt(0.05)) < 1e-10

        # Check sensitivity coefficients
        row1 = res.budget.get_row("X1")
        row2 = res.budget.get_row("X2")
        assert abs(float(row1.sensitivity_coefficient) - 1.0) < 1e-6
        assert abs(float(row2.sensitivity_coefficient) - 1.0) < 1e-6

        # Variance contributions: (0.1)^2 = 0.01 (20%), (0.2)^2 = 0.04 (80%)
        assert abs(float(row1.variance_contribution) - 0.01) < 1e-10
        assert abs(float(row2.variance_contribution) - 0.04) < 1e-10
        assert abs(float(row1.relative_contribution_pct) - 20.0) < 0.1
        assert abs(float(row2.relative_contribution_pct) - 80.0) < 0.1

    def test_case_b_product_independent(self):
        """Case B: Y = X1 * X2 (independent inputs).
        X1 = 10, u1 = 0.1
        X2 = 5, u2 = 0.05
        c1 = dY/dX1 = X2 = 5
        c2 = dY/dX2 = X1 = 10
        u1(y) = 5 * 0.1 = 0.5
        u2(y) = 10 * 0.05 = 0.5
        u_c = sqrt(0.5^2 + 0.5^2) = sqrt(0.5) ~= 0.7071068
        """
        model = MeasurementModel(
            measurand="P",
            equation="X1 * X2",
            input_names=("X1", "X2"),
            output_unit="W",
        )
        inputs = {
            "X1": InputQuantity.explicit("X1", 10.0, 0.1, unit="V"),
            "X2": InputQuantity.explicit("X2", 5.0, 0.05, unit="A"),
        }
        res = evaluate_gum(model, inputs)
        assert abs(float(res.measurand_value) - 50.0) < 1e-12
        assert abs(float(res.combined_standard_uncertainty) - math.sqrt(0.5)) < 1e-10

        # Relative uncertainty = u_c / P = sqrt((0.1/10)^2 + (0.05/5)^2) = sqrt(0.01^2 + 0.01^2)
        rel_u = float(res.combined_standard_uncertainty) / float(res.measurand_value)
        assert abs(rel_u - math.sqrt(2) * 0.01) < 1e-10

    def test_case_c_voltage_divider(self):
        """Case C: Voltage Divider Vout = Vin * R2 / (R1 + R2).
        Vin = 10 V, u(Vin) = 0.05 V
        R1 = 1000 ohm, u(R1) = 10 ohm
        R2 = 1000 ohm, u(R2) = 10 ohm
        Vout = 5.0 V
        c_Vin = R2 / (R1 + R2) = 0.5
        c_R1 = -Vin * R2 / (R1 + R2)^2 = -10 * 1000 / 2000^2 = -0.0025 V/ohm
        c_R2 = Vin * R1 / (R1 + R2)^2 = 10 * 1000 / 2000^2 = +0.0025 V/ohm
        u_Vin(y) = 0.5 * 0.05 = 0.025 V
        u_R1(y) = -0.0025 * 10 = -0.025 V
        u_R2(y) = 0.0025 * 10 = 0.025 V
        u_c = sqrt(0.025^2 + (-0.025)^2 + 0.025^2) = sqrt(3 * 0.000625) = sqrt(0.001875) ~= 0.04330127 V
        """
        model = MeasurementModel(
            measurand="Vout",
            equation="Vin * R2 / (R1 + R2)",
            input_names=("Vin", "R1", "R2"),
            output_unit="V",
        )
        inputs = {
            "Vin": InputQuantity.explicit("Vin", 10.0, 0.05, unit="V"),
            "R1": InputQuantity.explicit("R1", 1000.0, 10.0, unit="ohm"),
            "R2": InputQuantity.explicit("R2", 1000.0, 10.0, unit="ohm"),
        }
        res = evaluate_gum(model, inputs)
        assert abs(float(res.measurand_value) - 5.0) < 1e-12

        expected_uc = math.sqrt(3 * (0.025 ** 2))
        assert abs(float(res.combined_standard_uncertainty) - expected_uc) < 1e-6

        # Check sensitivities
        assert abs(float(res.budget.get_row("Vin").sensitivity_coefficient) - 0.5) < 1e-5
        assert abs(float(res.budget.get_row("R1").sensitivity_coefficient) - (-0.0025)) < 1e-5
        assert abs(float(res.budget.get_row("R2").sensitivity_coefficient) - 0.0025) < 1e-5

    def test_case_d_correlation_positive_and_negative_one(self):
        """Case D: Y = X1 + X2 with correlation r = +1 and r = -1.
        X1: u1 = 0.1
        X2: u2 = 0.2
        c1 = 1, c2 = 1
        r = +1: u_c = u1 + u2 = 0.3
        r = -1: u_c = |u1 - u2| = 0.1
        """
        model = MeasurementModel(
            measurand="Y",
            equation="X1 + X2",
            input_names=("X1", "X2"),
            output_unit="V",
        )
        inputs = {
            "X1": InputQuantity.explicit("X1", 10.0, 0.1, unit="V"),
            "X2": InputQuantity.explicit("X2", 20.0, 0.2, unit="V"),
        }

        # Perfectly correlated r = +1
        corr_pos = CorrelationMatrix()
        corr_pos.set_correlation("X1", "X2", 1.0)
        res_pos = evaluate_gum(model, inputs, correlation=corr_pos)
        assert abs(float(res_pos.combined_standard_uncertainty) - 0.3) < 1e-10

        # Perfectly anti-correlated r = -1
        corr_neg = CorrelationMatrix()
        corr_neg.set_correlation("X1", "X2", -1.0)
        res_neg = evaluate_gum(model, inputs, correlation=corr_neg)
        assert abs(float(res_neg.combined_standard_uncertainty) - 0.1) < 1e-10

    def test_case_e_type_a_evaluation_from_observations(self):
        """Case E: Type A evaluation from a series of measurements."""
        obs = [100.02, 100.05, 99.98, 100.01, 100.04, 99.99, 100.03, 100.00]
        q = InputQuantity.from_observations("L", obs, unit="mm")

        model = MeasurementModel(
            measurand="Length",
            equation="L",
            input_names=("L",),
            output_unit="mm",
        )
        res = evaluate_gum(model, {"L": q})
        assert q.degrees_of_freedom == 7.0
        assert res.effective_degrees_of_freedom == 7.0
        # Student's t k for nu = 7 at 95% is approx 2.365
        k_val = float(res.coverage_factor)
        assert abs(k_val - 2.365) < 0.02
        assert float(res.expanded_uncertainty) == pytest.approx(
            k_val * float(res.combined_standard_uncertainty), rel=1e-6
        )

    def test_case_f_type_b_rectangular(self):
        """Case F: Type B evaluation with rectangular distribution.
        a = 0.3 -> u = 0.3 / sqrt(3) ~= 0.173205
        """
        q = InputQuantity.rectangular("delta", nominal_value=0.0, half_width=0.3, unit="V")
        assert q.distribution == UncertaintyDistribution.RECTANGULAR
        assert math.isinf(q.degrees_of_freedom)
        assert abs(float(q.standard_uncertainty) - (0.3 / math.sqrt(3))) < 1e-10

        model = MeasurementModel(
            measurand="delta_out",
            equation="delta",
            input_names=("delta",),
            output_unit="V",
        )
        res = evaluate_gum(model, {"delta": q})
        assert math.isinf(res.effective_degrees_of_freedom)
        # For nu_eff = inf, k at 95% is 1.960
        assert abs(float(res.coverage_factor) - 1.960) < 0.005

    def test_case_g_type_b_triangular(self):
        """Case G: Type B evaluation with triangular distribution.
        a = 0.3 -> u = 0.3 / sqrt(6) ~= 0.122474
        """
        q = InputQuantity.triangular("delta", nominal_value=0.0, half_width=0.3, unit="V")
        assert q.distribution == UncertaintyDistribution.TRIANGULAR
        assert math.isinf(q.degrees_of_freedom)
        assert abs(float(q.standard_uncertainty) - (0.3 / math.sqrt(6))) < 1e-10

    def test_case_h_type_b_normal(self):
        """Case H: Type B evaluation with normal distribution from certificate.
        U = 0.5 V, k = 2.0 -> u = 0.25 V
        """
        q = InputQuantity.normal("V_cal", nominal_value=12.0, expanded_uncertainty=0.5, k=2.0, unit="V")
        assert q.distribution == UncertaintyDistribution.NORMAL
        assert abs(float(q.standard_uncertainty) - 0.25) < 1e-10

    def test_case_i_welch_satterthwaite_finite_dof(self):
        """Case I: Welch-Satterthwaite formula with finite degrees of freedom.
        Y = X1 + X2
        u1 = 0.1, nu1 = 9
        u2 = 0.2, nu2 = 4
        c1 = 1, c2 = 1
        uc^2 = 0.01 + 0.04 = 0.05 -> uc^4 = 0.0025
        term1 = (0.1)^4 / 9 = 0.0001 / 9 = 1.11111e-5
        term2 = (0.2)^4 / 4 = 0.0016 / 4 = 0.0004
        denom = 0.000411111...
        nu_eff = 0.0025 / 0.000411111... = 6.081
        """
        model = MeasurementModel(
            measurand="Y",
            equation="X1 + X2",
            input_names=("X1", "X2"),
            output_unit="V",
        )
        inputs = {
            "X1": InputQuantity(
                name="X1",
                nominal_value=10.0,
                standard_uncertainty=0.1,
                degrees_of_freedom=9.0,
                unit="V",
            ),
            "X2": InputQuantity(
                name="X2",
                nominal_value=20.0,
                standard_uncertainty=0.2,
                degrees_of_freedom=4.0,
                unit="V",
            ),
        }
        res = evaluate_gum(model, inputs)
        expected_nu_eff = 0.0025 / (0.0001 / 9.0 + 0.0016 / 4.0)
        assert abs(res.effective_degrees_of_freedom - expected_nu_eff) < 0.01

        # Now test Welch-Satterthwaite when one component has infinite dof:
        # X1 has nu1 = inf -> term1 = 0
        # denom = 0.0004
        # nu_eff = 0.0025 / 0.0004 = 6.25
        inputs["X1"] = InputQuantity.rectangular("X1", 10.0, half_width=0.1 * math.sqrt(3), unit="V")
        res_inf = evaluate_gum(model, inputs)
        assert abs(res_inf.effective_degrees_of_freedom - 6.25) < 0.01

    def test_case_j_coverage_factor_small_nu_eff(self):
        """Case J: Small nu_eff producing k != 2.
        For nu_eff = 4, p = 0.95: k ~= 2.78 (Student's t), definitely != 2.0.
        """
        model = MeasurementModel(
            measurand="Y",
            equation="X1",
            input_names=("X1",),
            output_unit="V",
        )
        inputs = {
            "X1": InputQuantity(
                name="X1",
                nominal_value=10.0,
                standard_uncertainty=0.1,
                degrees_of_freedom=4.0,
                unit="V",
            ),
        }
        res = evaluate_gum(model, inputs)
        assert res.effective_degrees_of_freedom == 4.0
        k = float(res.coverage_factor)
        assert abs(k - 2.78) < 0.02
        assert k != 2.0

        # Also verify that explicit user k is honored when requested
        res_explicit = evaluate_gum(model, inputs, explicit_k=2.0)
        assert float(res_explicit.coverage_factor) == 2.0
        assert float(res_explicit.expanded_uncertainty) == pytest.approx(0.2, rel=1e-6)


# ==============================================================================
# 5. Sensitivity Coefficient Calculation Modes
# ==============================================================================

class TestSensitivityCalculations:
    """Test explicit sensitivities, numerical differentiation, and custom evaluators."""

    def test_explicit_sensitivities(self):
        model = MeasurementModel(
            measurand="Y",
            equation="X1 * X2",
            input_names=("X1", "X2"),
            explicit_sensitivities={
                "X1": lambda vals: vals["X2"] * Decimal("2"),  # Arbitrary override
                "X2": lambda vals: vals["X1"],
            },
        )
        inputs = {
            "X1": InputQuantity.explicit("X1", 10.0, 0.1),
            "X2": InputQuantity.explicit("X2", 5.0, 0.05),
        }
        res = evaluate_gum(model, inputs)
        row1 = res.budget.get_row("X1")
        assert abs(float(row1.sensitivity_coefficient) - 10.0) < 1e-6  # 5 * 2
        assert row1.sensitivity_method == SensitivityMethod.EXPLICIT

    def test_numerical_sensitivities_central_difference(self):
        # Nonlinear function: Y = X1^2 + sin(X2)
        model = MeasurementModel(
            measurand="Y",
            equation="X1^2 + sin(X2)",
            input_names=("X1", "X2"),
        )
        inputs = {
            "X1": InputQuantity.explicit("X1", 3.0, 0.01),
            "X2": InputQuantity.explicit("X2", 0.0, 0.01),
        }
        res = evaluate_gum(model, inputs)
        # dY/dX1 = 2 * X1 = 6.0
        # dY/dX2 = cos(0) = 1.0
        row1 = res.budget.get_row("X1")
        row2 = res.budget.get_row("X2")
        assert abs(float(row1.sensitivity_coefficient) - 6.0) < 1e-5
        assert abs(float(row2.sensitivity_coefficient) - 1.0) < 1e-5
        assert row1.sensitivity_method == SensitivityMethod.NUMERICAL

    def test_custom_evaluator(self):
        # Using a custom pure-Python callable
        def custom_f(vals):
            return vals["A"] * vals["B"] + vals["C"]

        model = MeasurementModel(
            measurand="Out",
            input_names=("A", "B", "C"),
            evaluator=custom_f,
        )
        inputs = {
            "A": InputQuantity.explicit("A", 2.0, 0.1),
            "B": InputQuantity.explicit("B", 3.0, 0.1),
            "C": InputQuantity.explicit("C", 4.0, 0.1),
        }
        res = evaluate_gum(model, inputs)
        assert abs(float(res.measurand_value) - 10.0) < 1e-12


# ==============================================================================
# 6. Uncertainty Budget Table & Serialization
# ==============================================================================

class TestUncertaintyBudget:
    """Validate budget sorting, markdown rendering, and dictionary serialization."""

    def test_budget_sorting_and_table(self):
        model = MeasurementModel(
            measurand="Y",
            equation="X1 + X2 + X3",
            input_names=("X1", "X2", "X3"),
            output_unit="V",
        )
        inputs = {
            "X1": InputQuantity.explicit("X1", 1.0, 0.01, unit="V"),
            "X2": InputQuantity.explicit("X2", 2.0, 0.50, unit="V"),  # Dominant
            "X3": InputQuantity.explicit("X3", 3.0, 0.10, unit="V"),
        }
        res = evaluate_gum(model, inputs)
        budget = res.budget

        # Sort by contribution descending
        sorted_by_contrib = budget.by_contribution(descending=True)
        assert [r.quantity for r in sorted_by_contrib] == ["X2", "X3", "X1"]

        # Sort by name
        sorted_by_name = budget.by_name()
        assert [r.quantity for r in sorted_by_name] == ["X1", "X2", "X3"]

        # Check total relative contributions sum to 100%
        total_pct = sum(r.relative_contribution_pct for r in budget.rows)
        assert abs(float(total_pct) - 100.0) < 0.1

        # Markdown representation contains key columns
        md = budget.to_markdown()
        assert "| Quantity | Nominal | Unit | Type | Dist |" in md
        assert "X2" in md
        assert "Expanded Uncertainty (U)" in md

        # Dictionary serialization
        d = budget.to_dict()
        assert d["measurand"] == "Y"
        assert len(d["rows"]) == 3


# ==============================================================================
# 7. Provenance and CAS Storage Integration
# ==============================================================================

class TestProvenanceAndCAS:
    """Verify execution provenance and CAS artifact storage."""

    def test_cas_storage(self, tmp_path):
        cas = FileBlobStore(tmp_path / "cas")
        model = MeasurementModel(
            measurand="Y",
            equation="A * B",
            input_names=("A", "B"),
        )
        inputs = {
            "A": InputQuantity.explicit("A", 10.0, 0.1),
            "B": InputQuantity.explicit("B", 20.0, 0.2),
        }
        res = evaluate_gum(model, inputs, cas_store=cas)
        assert res.raw_artifact_hash != ""

        # Retrieve bytes from CAS
        stored_bytes = cas.get_bytes(res.raw_artifact_hash)
        assert stored_bytes is not None
        import json
        payload = json.loads(stored_bytes.decode("utf-8"))
        assert payload["standard"] == "ISO/IEC Guide 98-3 (GUM)"
        assert payload["measurand"] == "Y"


# ==============================================================================
# 8. End-to-End Integration via EngineeringService
# ==============================================================================

class TestEngineeringServiceGUMIntegration:
    """Validate GUM uncertainty evaluation through EngineeringService."""

    def test_service_evaluation(self, tmp_path):
        db = Database(tmp_path / "academic.db")
        repo = EngineeringRepository(db)
        service = EngineeringService(repo=repo)

        model = MeasurementModel(
            measurand="Power",
            equation="V * I",
            input_names=("V", "I"),
            output_unit="W",
        )
        inputs = {
            "V": InputQuantity.normal("V", 230.0, expanded_uncertainty=2.3, k=2.0, unit="V"),
            "I": InputQuantity.rectangular("I", 10.0, half_width=0.1, unit="A"),
        }

        res = service.evaluate_measurement_uncertainty(
            model=model,
            inputs=inputs,
            coverage_probability=0.95,
        )

        assert isinstance(res, GUMResult)
        assert res.measurand == "Power"
        assert abs(float(res.measurand_value) - 2300.0) < 1e-10
        assert float(res.combined_standard_uncertainty) > 0
        assert float(res.expanded_uncertainty) > float(res.combined_standard_uncertainty)
        assert res.measurand_unit == "W"


# ==============================================================================
# 9. Post-Audit Hardening: Positive Semi-Definite (PSD) Validation (Finding 1)
# ==============================================================================

class TestPSDValidationFinding1:
    """Rigorous tests A through I for Positive Semi-Definite (PSD) validation."""

    def test_case_a_identity_3x3_pass(self):
        """A) Identity 3x3 correlation matrix must PASS."""
        corr = CorrelationMatrix()
        eigs = corr.validate_psd(["X1", "X2", "X3"], tol=1e-7)
        assert len(eigs) == 3
        for e in eigs:
            assert abs(e - 1.0) < 1e-12

    def test_case_b_valid_matrix_pass(self):
        """B) Valid matrix with r12=0.5, r13=0.2, r23=0.3 must PASS."""
        corr = CorrelationMatrix.from_dict({
            ("X1", "X2"): 0.5,
            ("X1", "X3"): 0.2,
            ("X2", "X3"): 0.3,
        })
        eigs = corr.validate_psd(tol=1e-7)
        assert len(eigs) == 3
        assert min(eigs) > 0.0
        assert abs(eigs[0] - 0.48716) < 1e-3

    def test_case_c_perfect_correlation_pass(self):
        """C) Perfect correlation r12=1 must PASS."""
        corr = CorrelationMatrix.from_dict({
            ("X1", "X2"): 1.0,
        })
        eigs = corr.validate_psd(tol=1e-7)
        assert len(eigs) == 2
        assert abs(eigs[0] - 0.0) < 1e-12
        assert abs(eigs[1] - 2.0) < 1e-12

    def test_case_d_perfect_negative_correlation_pass(self):
        """D) Perfect negative correlation r12=-1 must PASS when resulting matrix is PSD."""
        corr = CorrelationMatrix.from_dict({
            ("X1", "X2"): -1.0,
        })
        eigs = corr.validate_psd(tol=1e-7)
        assert len(eigs) == 2
        assert abs(eigs[0] - 0.0) < 1e-12
        assert abs(eigs[1] - 2.0) < 1e-12

    def test_case_e_symmetric_non_psd_reject(self):
        """E) Symmetric matrix but NOT PSD must REJECT."""
        # Non-PSD case 1: r12=0.9, r13=0.9, r23=0.0 -> min eigenvalue ~= -0.273
        with pytest.raises(ValueError, match="not positive semi-definite.*minimum eigenvalue"):
            CorrelationMatrix.from_dict({
                ("X1", "X2"): 0.9,
                ("X1", "X3"): 0.9,
                ("X2", "X3"): 0.0,
            })

        # Non-PSD case 2: r12=0.8, r13=0.8, r23=-0.8 -> min eigenvalue ~= -0.44
        with pytest.raises(ValueError, match="not positive semi-definite.*minimum eigenvalue"):
            CorrelationMatrix.from_dict({
                ("X1", "X2"): 0.8,
                ("X1", "X3"): 0.8,
                ("X2", "X3"): -0.8,
            })

    def test_case_f_r_greater_than_one_reject(self):
        """F) r > 1 must REJECT."""
        corr = CorrelationMatrix()
        with pytest.raises(ValueError, match="out of range"):
            corr.set_correlation("X1", "X2", 1.0001)

    def test_case_g_r_less_than_minus_one_reject(self):
        """G) r < -1 must REJECT."""
        corr = CorrelationMatrix()
        with pytest.raises(ValueError, match="out of range"):
            corr.set_correlation("X1", "X2", -1.0001)

    def test_case_h_diagonal_not_one_reject(self):
        """H) diagonal != 1 must REJECT."""
        corr = CorrelationMatrix()
        with pytest.raises(ValueError, match="diagonal correlation"):
            corr.set_correlation("X1", "X1", 0.99)

    def test_case_i_eigenvalue_zero_tolerance_pass(self):
        """I) PSD matrix with eigenvalue approximately 0 must PASS within tolerance."""
        corr = CorrelationMatrix.from_dict({
            ("X1", "X2"): 1.0,
            ("X1", "X3"): 0.0,
            ("X2", "X3"): 0.0,
        })
        eigs = corr.validate_psd(tol=1e-7)
        assert len(eigs) == 3
        assert abs(eigs[0]) < 1e-7
        assert abs(eigs[1] - 1.0) < 1e-12
        assert abs(eigs[2] - 2.0) < 1e-12

    def test_psd_validation_in_evaluate_gum(self):
        """evaluate_gum must validate PSD on the active model variables and reject non-PSD matrices."""
        model = MeasurementModel(
            measurand="Y",
            equation="X1 + X2 + X3",
            input_names=("X1", "X2", "X3"),
            output_unit="V",
        )
        inputs = {
            "X1": InputQuantity.explicit("X1", 10.0, 0.1, unit="V"),
            "X2": InputQuantity.explicit("X2", 10.0, 0.1, unit="V"),
            "X3": InputQuantity.explicit("X3", 10.0, 0.1, unit="V"),
        }
        # Construct non-PSD manually bypassing post_init
        bad_corr = CorrelationMatrix()
        bad_corr.correlations[("X1", "X2")] = Decimal("0.9")
        bad_corr.correlations[("X2", "X1")] = Decimal("0.9")
        bad_corr.correlations[("X1", "X3")] = Decimal("0.9")
        bad_corr.correlations[("X3", "X1")] = Decimal("0.9")
        bad_corr.correlations[("X2", "X3")] = Decimal("0.0")
        bad_corr.correlations[("X3", "X2")] = Decimal("0.0")

        with pytest.raises(ValueError, match="not positive semi-definite"):
            evaluate_gum(model, inputs, correlation=bad_corr)


# ==============================================================================
# 10. Post-Audit Hardening: Real Dimensional Validation (Finding 2)
# ==============================================================================

class TestDimensionalValidationFinding2:
    """Mandatory dimensional tests 1 through 8 from audit specification."""

    def test_req_1_v_div_ohm_equals_ampere(self):
        """Test 1: X1 = 10 V, X2 = 2 Ω, Y = X1 / X2 -> 5 A."""
        model = MeasurementModel(
            measurand="I",
            equation="X1 / X2",
            input_names=("X1", "X2"),
        )
        inputs = {
            "X1": InputQuantity.explicit("X1", 10.0, 0.1, unit="V"),
            "X2": InputQuantity.explicit("X2", 2.0, 0.05, unit="Ω"),
        }
        res = evaluate_gum(model, inputs)
        assert abs(float(res.measurand_value) - 5.0) < 1e-12
        assert res.measurand_unit == "A"
        assert res.budget.measurand_unit == "A"

    def test_req_2_v_mul_ampere_equals_watt(self):
        """Test 2: X1 = 2 V, X2 = 3 A, Y = X1 * X2 -> 6 W."""
        model = MeasurementModel(
            measurand="P",
            equation="X1 * X2",
            input_names=("X1", "X2"),
        )
        inputs = {
            "X1": InputQuantity.explicit("X1", 2.0, 0.02, unit="V"),
            "X2": InputQuantity.explicit("X2", 3.0, 0.03, unit="A"),
        }
        res = evaluate_gum(model, inputs)
        assert abs(float(res.measurand_value) - 6.0) < 1e-12
        assert res.measurand_unit == "W"
        assert res.budget.measurand_unit == "W"

    def test_req_3_v_div_ampere_equals_ohm(self):
        """Test 3: X1 = 10 V, X2 = 2 A, Y = X1 / X2 -> 5 Ω."""
        model = MeasurementModel(
            measurand="R",
            equation="X1 / X2",
            input_names=("X1", "X2"),
        )
        inputs = {
            "X1": InputQuantity.explicit("X1", 10.0, 0.1, unit="V"),
            "X2": InputQuantity.explicit("X2", 2.0, 0.05, unit="A"),
        }
        res = evaluate_gum(model, inputs)
        assert abs(float(res.measurand_value) - 5.0) < 1e-12
        assert res.measurand_unit in ("Ω", "ohm")
        assert res.budget.measurand_unit in ("Ω", "ohm")

    def test_req_4_incompatible_addition_v_plus_s_rejected(self):
        """Test 4: V + s -> REJECT."""
        from academic_core.domain.engineering.units import UnitError
        model = MeasurementModel(
            measurand="Y",
            equation="X1 + X2",
            input_names=("X1", "X2"),
        )
        inputs = {
            "X1": InputQuantity.explicit("X1", 10.0, 0.1, unit="V"),
            "X2": InputQuantity.explicit("X2", 2.0, 0.05, unit="s"),
        }
        with pytest.raises(UnitError, match="incompatible dimensions"):
            evaluate_gum(model, inputs)

    def test_req_5_incompatible_addition_v_plus_a_rejected(self):
        """Test 5: V + A -> REJECT."""
        from academic_core.domain.engineering.units import UnitError
        model = MeasurementModel(
            measurand="Y",
            equation="X1 + X2",
            input_names=("X1", "X2"),
        )
        inputs = {
            "X1": InputQuantity.explicit("X1", 10.0, 0.1, unit="V"),
            "X2": InputQuantity.explicit("X2", 2.0, 0.05, unit="A"),
        }
        with pytest.raises(UnitError, match="incompatible dimensions"):
            evaluate_gum(model, inputs)

    def test_req_5b_incompatible_addition_a_plus_ohm_rejected(self):
        """Incompatible addition: A + Ω -> REJECT."""
        from academic_core.domain.engineering.units import UnitError
        model = MeasurementModel(
            measurand="Y",
            equation="X1 + X2",
            input_names=("X1", "X2"),
        )
        inputs = {
            "X1": InputQuantity.explicit("X1", 1.0, 0.01, unit="A"),
            "X2": InputQuantity.explicit("X2", 10.0, 0.1, unit="Ω"),
        }
        with pytest.raises(UnitError, match="incompatible dimensions"):
            evaluate_gum(model, inputs)

    def test_req_6_incompatible_output_unit_rejected(self):
        """Test 6: output_unit incompatible with calculated unit -> REJECT."""
        from academic_core.domain.engineering.units import UnitError
        model = MeasurementModel(
            measurand="I",
            equation="X1 / X2",
            input_names=("X1", "X2"),
            output_unit="V",
        )
        inputs = {
            "X1": InputQuantity.explicit("X1", 10.0, 0.1, unit="V"),
            "X2": InputQuantity.explicit("X2", 2.0, 0.05, unit="Ω"),
        }
        with pytest.raises(UnitError, match="incompatible with declared output_unit"):
            evaluate_gum(model, inputs)

    def test_req_7_correct_output_unit_pass(self):
        """Test 7: output_unit correct -> PASS."""
        model = MeasurementModel(
            measurand="I",
            equation="X1 / X2",
            input_names=("X1", "X2"),
            output_unit="A",
        )
        inputs = {
            "X1": InputQuantity.explicit("X1", 10.0, 0.1, unit="V"),
            "X2": InputQuantity.explicit("X2", 2.0, 0.05, unit="Ω"),
        }
        res = evaluate_gum(model, inputs)
        assert abs(float(res.measurand_value) - 5.0) < 1e-12
        assert res.measurand_unit == "A"

    def test_req_8_existing_equations_continue_working(self):
        """Test 8: Existing GUM equations from F7-B7 continue working."""
        m_sum = MeasurementModel(measurand="Vtot", equation="V1 + V2", output_unit="V")
        res_sum = evaluate_gum(m_sum, {
            "V1": InputQuantity.explicit("V1", 5.0, 0.05, unit="V"),
            "V2": InputQuantity.explicit("V2", 7.0, 0.07, unit="V"),
        })
        assert float(res_sum.measurand_value) == 12.0
        assert res_sum.measurand_unit == "V"


# ==============================================================================
# 11. Post-Audit Hardening: Numerical Sensitivity Precision (Finding 3)
# ==============================================================================

class TestSensitivityPrecisionFinding3:
    """Validate that numerical sensitivities preserve full precision (> 9 decimal places)."""

    def test_numerical_sensitivity_preserves_precision_beyond_9_decimals(self):
        val_str = "1.23456789123456"
        model = MeasurementModel(
            measurand="Y",
            equation="X1**3 / 7",
            input_names=("X1",),
        )
        x_nom = Decimal(val_str)
        inputs = {"X1": x_nom}
        c_num, method = model.get_sensitivity("X1", inputs)
        assert method == SensitivityMethod.NUMERICAL.value

        c_exact = (Decimal("3") * (x_nom ** 2)) / Decimal("7")
        diff = abs(c_num - c_exact)
        assert diff < Decimal("1e-9")

        s = str(c_num)
        frac = s.split(".")[1] if "." in s else ""
        assert len(frac) > 9
        assert frac[9:12] != "000"


# ==============================================================================
# 12. Post-Audit Hardening: Explicit k Validation & Provenance (Finding 4)
# ==============================================================================

class TestExplicitKValidationFinding4:
    """Validate explicit_k requirements: k > 0, reject <=0, NaN, Inf, and check provenance."""

    def test_explicit_k_positive_pass(self):
        model = MeasurementModel(measurand="Y", equation="X", output_unit="V")
        inputs = {"X": InputQuantity.explicit("X", 10.0, 0.5, unit="V")}
        res = evaluate_gum(model, inputs, explicit_k=2.5)
        assert res.coverage_factor == Decimal("2.5")
        assert res.expanded_uncertainty == Decimal("2.5") * Decimal("0.5")
        assert res.provenance["coverage_factor_source"] == "explicit_user"

    def test_explicit_k_zero_rejected(self):
        model = MeasurementModel(measurand="Y", equation="X", output_unit="V")
        inputs = {"X": InputQuantity.explicit("X", 10.0, 0.5, unit="V")}
        with pytest.raises(ValueError, match="strictly positive"):
            evaluate_gum(model, inputs, explicit_k=0.0)

    def test_explicit_k_negative_rejected(self):
        model = MeasurementModel(measurand="Y", equation="X", output_unit="V")
        inputs = {"X": InputQuantity.explicit("X", 10.0, 0.5, unit="V")}
        with pytest.raises(ValueError, match="strictly positive"):
            evaluate_gum(model, inputs, explicit_k=-2.0)

    def test_explicit_k_nan_rejected(self):
        model = MeasurementModel(measurand="Y", equation="X", output_unit="V")
        inputs = {"X": InputQuantity.explicit("X", 10.0, 0.5, unit="V")}
        with pytest.raises(ValueError, match="strictly positive"):
            evaluate_gum(model, inputs, explicit_k=float("nan"))

    def test_explicit_k_inf_rejected(self):
        model = MeasurementModel(measurand="Y", equation="X", output_unit="V")
        inputs = {"X": InputQuantity.explicit("X", 10.0, 0.5, unit="V")}
        with pytest.raises(ValueError, match="strictly positive"):
            evaluate_gum(model, inputs, explicit_k=float("inf"))

    def test_coverage_factor_provenance_distinctions(self):
        model = MeasurementModel(measurand="Y", equation="X", output_unit="V")

        # 1. Finite dof -> student_t
        inputs_finite = {"X": InputQuantity("X", Decimal("10"), standard_uncertainty=Decimal("0.5"), degrees_of_freedom=5.0, unit="V")}
        res_t = evaluate_gum(model, inputs_finite)
        assert res_t.provenance["coverage_factor_source"] == "student_t"

        # 2. Infinite dof -> normal_limit
        inputs_inf = {"X": InputQuantity.rectangular("X", 10.0, half_width=0.5, unit="V")}
        res_norm = evaluate_gum(model, inputs_inf)
        assert res_norm.provenance["coverage_factor_source"] == "normal_limit"

        # 3. Explicit user override -> explicit_user
        res_exp = evaluate_gum(model, inputs_inf, explicit_k=3.0)
        assert res_exp.provenance["coverage_factor_source"] == "explicit_user"


# ==============================================================================
# 13. Final Post-Audit Hardening: LENGTH dimension, no synthetic units (Finding 1-3, 7)
# ==============================================================================

class TestLengthDimensionAndNoSyntheticUnits:
    """Mandatory tests A through L from the final post-audit remediation spec.

    Proves mm/cm/km/m share a real LENGTH dimension sourced solely from
    units.py::parse_unit(), and that unknown units are rejected rather than
    silently converted into a fabricated dimension.
    """

    def test_a_length_dimension_shared_across_prefixes(self):
        assert parse_unit("m").dimension == LENGTH
        assert parse_unit("mm").dimension == LENGTH
        assert parse_unit("cm").dimension == LENGTH
        assert parse_unit("km").dimension == LENGTH

    def test_b_scale_m_to_mm(self):
        q = Quantity(Decimal("1"), parse_unit("m"))
        converted = q.convert_to("mm")
        assert converted.value == Decimal("1000")

    def test_c_scale_mm_to_m(self):
        q = Quantity(Decimal("1"), parse_unit("mm"))
        converted = q.convert_to("m")
        assert converted.value == Decimal("0.001")

    def test_d_scale_100mm_to_m(self):
        q = Quantity(Decimal("100"), parse_unit("mm"))
        converted = q.convert_to("m")
        assert converted.value == Decimal("0.1")

    def test_e_unknown_unit_rejected(self):
        with pytest.raises(UnitError):
            parse_unit("unknown_unit")

    def test_f_measurement_model_unknown_input_unit_rejected(self):
        model = MeasurementModel(measurand="Y", equation="X", output_unit="")
        with pytest.raises(UnitError):
            evaluate_gum(model, {"X": InputQuantity.explicit("X", 10.0, 0.1, unit="unknown_unit")})

    def test_g_measurement_model_unknown_output_unit_rejected(self):
        model = MeasurementModel(measurand="Y", equation="X", output_unit="unknown_unit")
        with pytest.raises(UnitError):
            evaluate_gum(model, {"X": InputQuantity.explicit("X", 10.0, 0.1, unit="mm")})

    def test_h_division_preserves_length_dimension(self):
        model = MeasurementModel(measurand="Y", equation="X / 2", input_names=("X",))
        res = evaluate_gum(model, {"X": InputQuantity.explicit("X", 100.0, 1.0, unit="mm")})
        assert res.budget.rows[0].unit == "mm"
        q = model.evaluate_to_quantity({"X": Decimal("100")}, input_units={"X": "mm"})
        assert q.dimension == LENGTH

    def test_i_division_with_output_unit_conversion(self):
        model = MeasurementModel(measurand="Y", equation="X / 2", input_names=("X",), output_unit="m")
        res = evaluate_gum(model, {"X": InputQuantity.explicit("X", 100.0, 1.0, unit="mm")})
        assert res.measurand_unit == "m"
        assert abs(float(res.measurand_value) - 0.05) < 1e-12

    def test_j_cross_dimension_length_plus_time_rejected(self):
        model = MeasurementModel(measurand="Y", equation="X1 + X2", input_names=("X1", "X2"))
        inputs = {
            "X1": InputQuantity.explicit("X1", 1.0, 0.01, unit="mm"),
            "X2": InputQuantity.explicit("X2", 1.0, 0.01, unit="s"),
        }
        with pytest.raises(UnitError, match="incompatible dimensions"):
            evaluate_gum(model, inputs)

    def test_k_cross_dimension_length_plus_voltage_rejected(self):
        model = MeasurementModel(measurand="Y", equation="X1 + X2", input_names=("X1", "X2"))
        inputs = {
            "X1": InputQuantity.explicit("X1", 1.0, 0.01, unit="mm"),
            "X2": InputQuantity.explicit("X2", 1.0, 0.01, unit="V"),
        }
        with pytest.raises(UnitError, match="incompatible dimensions"):
            evaluate_gum(model, inputs)

    def test_l_same_dimension_addition_m_plus_mm(self):
        q1 = Quantity(Decimal("1"), parse_unit("m"))
        q2 = Quantity(Decimal("100"), parse_unit("mm"))
        total = q1 + q2
        assert total.value == Decimal("1.1")
        assert total.unit.display == "m"


# ==============================================================================
# 14. Surgical Closure: evaluator dimensional bypass
# ==============================================================================

class TestEvaluatorDimensionalBypassClosed:
    """MeasurementModel.evaluator must not be able to escape the F6 dimensional
    system. When any unit is declared (input or output), the evaluator receives
    and must return Quantity; a Decimal result carries no dimension and cannot
    be silently labeled with output_unit.
    """

    def test_a_evaluator_dimensional_v_div_ohm_equals_a(self):
        model = MeasurementModel(
            measurand="I",
            evaluator=lambda x: x["V"] / x["R"],
            input_names=("V", "R"),
            output_unit="A",
        )
        inputs = {
            "V": InputQuantity.explicit("V", 10.0, 0.1, unit="V"),
            "R": InputQuantity.explicit("R", 1000.0, 10.0, unit="ohm"),
        }
        res = evaluate_gum(model, inputs)
        assert abs(float(res.measurand_value) - 0.01) < 1e-12
        assert res.measurand_unit == "A"

        q = model.evaluate_to_quantity(
            {"V": Decimal("10"), "R": Decimal("1000")},
            input_units={"V": "V", "R": "ohm"},
        )
        assert q.dimension == CURRENT

    def test_b_evaluator_cannot_sum_mm_plus_s(self):
        model = MeasurementModel(
            measurand="Y",
            evaluator=lambda x: x["X"] + x["T"],
            input_names=("X", "T"),
        )
        inputs = {
            "X": InputQuantity.explicit("X", 10.0, 0.1, unit="mm"),
            "T": InputQuantity.explicit("T", 2.0, 0.1, unit="s"),
        }
        with pytest.raises(UnitError):
            evaluate_gum(model, inputs)

    def test_c_evaluator_cannot_sum_mm_plus_v(self):
        model = MeasurementModel(
            measurand="Y",
            evaluator=lambda x: x["X"] + x["T"],
            input_names=("X", "T"),
        )
        inputs = {
            "X": InputQuantity.explicit("X", 10.0, 0.1, unit="mm"),
            "T": InputQuantity.explicit("T", 2.0, 0.1, unit="V"),
        }
        with pytest.raises(UnitError):
            evaluate_gum(model, inputs)

    def test_d_evaluator_output_incompatible_rejected(self):
        model = MeasurementModel(
            measurand="Y",
            evaluator=lambda x: Quantity(Decimal("10"), parse_unit("V")),
            input_names=("X",),
            input_units={"X": "V"},
            output_unit="A",
        )
        with pytest.raises(UnitError, match="incompatible with declared output_unit"):
            evaluate_gum(model, {"X": InputQuantity.explicit("X", 1.0, 0.01, unit="V")})

    def test_e_evaluator_output_compatible_converted(self):
        model = MeasurementModel(
            measurand="Y",
            evaluator=lambda x: Quantity(Decimal("100"), parse_unit("mm")),
            input_names=("X",),
            output_unit="m",
        )
        res = evaluate_gum(model, {"X": InputQuantity.explicit("X", 1.0, 0.01, unit="mm")})
        assert res.measurand_value == Decimal("0.1")
        assert res.measurand_unit == "m"

    def test_f_decimal_output_forbidden_in_dimensional_model(self):
        model = MeasurementModel(
            measurand="Y",
            evaluator=lambda x: Decimal("12"),
            input_names=("X",),
            input_units={"X": "mm"},
            output_unit="m",
        )
        with pytest.raises(UnitError, match="must return Quantity"):
            evaluate_gum(model, {"X": InputQuantity.explicit("X", 1.0, 0.01, unit="mm")})

    def test_g_evaluator_unknown_input_unit_rejected(self):
        model = MeasurementModel(
            measurand="Y",
            evaluator=lambda x: x["X"],
            input_names=("X",),
            input_units={"X": "totally_unknown_unit"},
        )
        with pytest.raises(UnitError):
            evaluate_gum(model, {"X": InputQuantity.explicit("X", 1.0, 0.01, unit="totally_unknown_unit")})

    def test_h_evaluator_unknown_output_unit_rejected(self):
        model = MeasurementModel(
            measurand="Y",
            evaluator=lambda x: Quantity(Decimal("1"), parse_unit("V")),
            input_names=("X",),
            output_unit="totally_unknown_unit",
        )
        with pytest.raises(UnitError):
            evaluate_gum(model, {"X": InputQuantity.explicit("X", 1.0, 0.01, unit="V")})

    def test_i_quantity_input_preserved_for_evaluator(self):
        received: dict[str, Quantity] = {}

        def ev(x):
            received["X"] = x["X"]
            return x["X"]

        model = MeasurementModel(
            measurand="Y", evaluator=ev, input_names=("X",), input_units={"X": "mm"},
        )
        q_in = Quantity(Decimal("100"), parse_unit("mm"))
        result = model.evaluate_to_quantity({"X": q_in})
        assert isinstance(received["X"], Quantity)
        assert received["X"] is q_in
        assert result.value == Decimal("100")

    def test_j_legacy_dimensionless_evaluator_still_uses_decimal(self):
        """No unit declared anywhere -> evaluator keeps the pre-existing Decimal contract."""
        def custom_f(vals):
            return vals["A"] * vals["B"] + vals["C"]

        model = MeasurementModel(
            measurand="Out", input_names=("A", "B", "C"), evaluator=custom_f,
        )
        inputs = {
            "A": InputQuantity.explicit("A", 2.0, 0.1),
            "B": InputQuantity.explicit("B", 3.0, 0.1),
            "C": InputQuantity.explicit("C", 4.0, 0.1),
        }
        res = evaluate_gum(model, inputs)
        assert abs(float(res.measurand_value) - 10.0) < 1e-12

    def test_regression_audited_bypass_mm_plus_s_must_fail(self):
        """Exact scenario from the audit: evaluator ignoring declared mm/s units
        and output_unit='mm' must NOT silently produce 12 mm."""
        model = MeasurementModel(
            measurand="Y",
            evaluator=lambda x: x["X"] + x["T"],
            input_units={"X": "mm", "T": "s"},
            output_unit="mm",
        )
        inputs = {
            "X": InputQuantity.explicit("X", 10.0, 0.1, unit="mm"),
            "T": InputQuantity.explicit("T", 2.0, 0.1, unit="s"),
        }
        with pytest.raises(UnitError):
            evaluate_gum(model, inputs)

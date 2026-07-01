"""Tests for severity mapper."""
import pytest
from app.utils.severity_mapper import SeverityMapper, map_osv_severity, get_cvss_score


class TestSeverityMapper:
    """Test cases for severity mapping."""

    def test_from_cvss_score_critical(self):
        """Test CRITICAL severity for CVSS score >= 9.0."""
        assert SeverityMapper.from_cvss_score(9.8) == "CRITICAL"
        assert SeverityMapper.from_cvss_score(10.0) == "CRITICAL"
        assert SeverityMapper.from_cvss_score(9.0) == "CRITICAL"

    def test_from_cvss_score_high(self):
        """Test HIGH severity for CVSS score 7.0-8.9."""
        assert SeverityMapper.from_cvss_score(8.6) == "HIGH"
        assert SeverityMapper.from_cvss_score(7.5) == "HIGH"
        assert SeverityMapper.from_cvss_score(7.0) == "HIGH"

    def test_from_cvss_score_medium(self):
        """Test MEDIUM severity for CVSS score 4.0-6.9."""
        assert SeverityMapper.from_cvss_score(6.5) == "MEDIUM"
        assert SeverityMapper.from_cvss_score(5.0) == "MEDIUM"
        assert SeverityMapper.from_cvss_score(4.0) == "MEDIUM"

    def test_from_cvss_score_low(self):
        """Test LOW severity for CVSS score 1.0-3.9."""
        assert SeverityMapper.from_cvss_score(3.5) == "LOW"
        assert SeverityMapper.from_cvss_score(2.0) == "LOW"
        assert SeverityMapper.from_cvss_score(1.0) == "LOW"

    def test_from_cvss_score_info(self):
        """Test INFO severity for CVSS score < 1.0."""
        assert SeverityMapper.from_cvss_score(0.5) == "INFO"
        assert SeverityMapper.from_cvss_score(0.0) == "INFO"

    def test_from_cvss_vector_with_score(self):
        """Test parsing CVSS vector with embedded score."""
        vector = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H (score: 9.8)"
        score = SeverityMapper.from_cvss_vector(vector)
        assert score == 9.8

    def test_from_cvss_vector_high_impact(self):
        """Test parsing CVSS vector with high impact indicators."""
        vector = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
        score = SeverityMapper.from_cvss_vector(vector)
        # Three high impacts should return 9.0
        assert score == 9.0

    def test_from_cvss_vector_empty(self):
        """Test parsing empty CVSS vector."""
        assert SeverityMapper.from_cvss_vector("") == 0.0
        assert SeverityMapper.from_cvss_vector(None) == 0.0

    def test_from_osv_with_cvss_score(self):
        """Test OSV severity extraction with numeric CVSS score."""
        vuln = {
            "id": "CVE-2021-44228",
            "severity": [{"type": "CVSS", "score": 9.8}]
        }
        assert SeverityMapper.from_osv(vuln) == "CRITICAL"

    def test_from_osv_with_cvss_vector(self):
        """Test OSV severity extraction with CVSS vector string."""
        vuln = {
            "id": "CVE-2021-001",
            "severity": [{"type": "CVSS", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}]
        }
        result = SeverityMapper.from_osv(vuln)
        assert result in ["CRITICAL", "HIGH"]

    def test_from_osv_without_cvss(self):
        """Test OSV severity inference without CVSS data."""
        vuln = {
            "id": "CVE-2021-001",
            "summary": "Remote code execution vulnerability",
            "severity": []
        }
        # Should infer from risk type keywords
        result = SeverityMapper.from_osv(vuln)
        assert result in ["CRITICAL", "HIGH", "MEDIUM"]

    def test_from_osv_known_critical(self):
        """Test OSV severity for known critical vulnerabilities."""
        vuln = {
            "id": "CVE-2021-44228",
            "summary": "Apache Log4j2 remote code execution",
            "aliases": ["GHSA-7rjr-3q55-vv33"],
            "severity": []
        }
        result = SeverityMapper.from_osv(vuln)
        assert result == "CRITICAL"

    def test_from_secret_type_critical(self):
        """Test secret type severity for critical secrets."""
        assert SeverityMapper.from_secret_type("private_key") == "CRITICAL"
        assert SeverityMapper.from_secret_type("aws_secret_key") == "CRITICAL"

    def test_from_secret_type_high(self):
        """Test secret type severity for high risk secrets."""
        assert SeverityMapper.from_secret_type("aws_access_key") == "HIGH"
        assert SeverityMapper.from_secret_type("github_token") == "HIGH"

    def test_from_secret_type_with_example_context(self):
        """Test secret type severity reduced for example files."""
        context = {"is_example": True}
        assert SeverityMapper.from_secret_type("private_key", context) == "INFO"

        context = {"has_example_keyword": True}
        assert SeverityMapper.from_secret_type("aws_access_key", context) == "MEDIUM"

    def test_get_cvss_score_numeric(self):
        """Test extracting numeric CVSS score."""
        vuln = {
            "severity": [{"type": "CVSS", "score": 7.5}]
        }
        assert SeverityMapper.get_cvss_score(vuln) == 7.5

    def test_get_cvss_score_missing(self):
        """Test CVSS score when no severity data."""
        vuln = {"severity": []}
        assert SeverityMapper.get_cvss_score(vuln) == 0.0

    def test_get_risk_type_rce(self):
        """Test risk type detection for RCE."""
        vuln = {"summary": "Remote code execution via crafted request"}
        assert "远程代码执行" in SeverityMapper.get_risk_type(vuln)

    def test_get_risk_type_injection(self):
        """Test risk type detection for injection."""
        vuln = {"summary": "SQL injection vulnerability in login"}
        result = SeverityMapper.get_risk_type(vuln)
        assert result == "注入漏洞"

    def test_get_risk_type_default(self):
        """Test default risk type for generic vulnerability."""
        vuln = {"summary": "A minor security issue"}
        assert SeverityMapper.get_risk_type(vuln) == "安全漏洞"


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_map_osv_severity(self):
        """Test map_osv_severity convenience function."""
        vuln = {"severity": [{"type": "CVSS", "score": 8.5}]}
        assert map_osv_severity(vuln) == "HIGH"

    def test_get_cvss_score(self):
        """Test get_cvss_score convenience function."""
        vuln = {"severity": [{"type": "CVSS", "score": 9.0}]}
        assert get_cvss_score(vuln) == 9.0
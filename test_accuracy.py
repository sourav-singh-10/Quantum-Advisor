"""
QuantumAdvisor Testing Suite
Tests backend API, frontend integration, and displays accuracy metrics
"""

import requests
import json
import time
from datetime import datetime
from colorama import Fore, Back, Style, init

# Initialize colorama for colored output
init(autoreset=True)

# Configuration
BACKEND_URL = "http://127.0.0.1:5000"
TEST_RESULTS = []

# Test cases with expected behaviors
TEST_CASES = [
    # Indian Stocks
    {
        'name': 'IOC Analysis - Experienced Investor',
        'ticker': 'IOC',
        'age': 30,
        'riskAppetite': 'Aggressive',
        'timeHorizon': 'Long-term',
        'portfolioValue': 100000,
        'experience': 'Experienced',
        'expected': {
            'has_price': True,
            'has_risk_score': True,
            'has_recommendation': True,
            'has_targets': True,
            'price_source': ['MarketStack', 'Verified Database'],
            'risk_score_range': (0, 100),
        }
    },
    {
        'name': 'RELIANCE Analysis - Beginner Investor',
        'ticker': 'RELIANCE',
        'age': 25,
        'riskAppetite': 'Conservative',
        'timeHorizon': 'Medium-term',
        'portfolioValue': 50000,
        'experience': 'Beginner',
        'expected': {
            'has_price': True,
            'has_risk_score': True,
            'recommendation': 'Start SIP',
            'has_portfolio_advice': True,
        }
    },
    {
        'name': 'TCS Analysis - High Risk Appetite',
        'ticker': 'TCS',
        'age': 35,
        'riskAppetite': 'Aggressive',
        'timeHorizon': 'Long-term',
        'portfolioValue': 200000,
        'experience': 'Experienced',
        'expected': {
            'has_price': True,
            'has_risk_score': True,
            'has_recommendation': True,
            'has_targets': True,
        }
    },
    # US Stocks
    {
        'name': 'AAPL Analysis - US Stock',
        'ticker': 'AAPL',
        'age': 40,
        'riskAppetite': 'Moderate',
        'timeHorizon': 'Medium-term',
        'portfolioValue': 150000,
        'experience': 'Experienced',
        'expected': {
            'has_price': True,
            'currency_conversion': True,  # Should convert USD to INR
            'has_risk_score': True,
        }
    },
    # Edge Cases
    {
        'name': 'Low Portfolio Value',
        'ticker': 'RELIANCE',
        'age': 22,
        'riskAppetite': 'Conservative',
        'timeHorizon': 'Short-term',
        'portfolioValue': 5000,
        'experience': 'Beginner',
        'expected': {
            'has_price': True,
            'has_risk_score': True,
        }
    },
    {
        'name': 'Elderly Investor',
        'ticker': 'IOC',
        'age': 65,
        'riskAppetite': 'Conservative',
        'timeHorizon': 'Short-term',
        'portfolioValue': 500000,
        'experience': 'Experienced',
        'expected': {
            'has_price': True,
            'has_risk_score': True,
            'lower_risk_capacity': True,  # Older age should reduce risk capacity
        }
    },
    {
        'name': 'Unknown Stock Symbol',
        'ticker': 'NOTASTOCK',
        'age': 30,
        'riskAppetite': 'Moderate',
        'timeHorizon': 'Medium-term',
        'portfolioValue': 50000,
        'experience': 'Experienced',
        'expected': {
            'has_price': True,  # Should use fallback price
            'has_risk_score': True,
        }
    },
]

def print_header(text):
    """Print colored header"""
    print("\n" + "="*70)
    print(Fore.CYAN + Style.BRIGHT + text.center(70))
    print("="*70)

def print_test_name(text):
    """Print test name"""
    print(Fore.YELLOW + f"\n📋 TEST: {text}")

def print_success(text):
    """Print success message"""
    print(Fore.GREEN + f"  ✅ {text}")

def print_error(text):
    """Print error message"""
    print(Fore.RED + f"  ❌ {text}")

def print_warning(text):
    """Print warning message"""
    print(Fore.YELLOW + f"  ⚠️  {text}")

def print_info(text):
    """Print info message"""
    print(Fore.CYAN + f"  ℹ️  {text}")

def check_backend_health():
    """Test if backend is running"""
    print_header("BACKEND HEALTH CHECK")
    try:
        response = requests.get(f"{BACKEND_URL}/api/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_success(f"Backend is running!")
            print_info(f"Status: {data.get('status')}")
            print_info(f"Version: {data.get('version')}")
            return True
        else:
            print_error(f"Backend returned status code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Cannot connect to backend: {e}")
        print_warning("Make sure backend is running on http://localhost:5000")
        return False

def run_test_case(test_case):
    """Run a single test case"""
    print_test_name(test_case['name'])
    
    result = {
        'name': test_case['name'],
        'ticker': test_case['ticker'],
        'passed': True,
        'checks': [],
        'response_time': 0,
        'response_data': None,
    }
    
    # Prepare request
    request_data = {
        'ticker': test_case['ticker'],
        'age': test_case['age'],
        'riskAppetite': test_case['riskAppetite'],
        'timeHorizon': test_case['timeHorizon'],
        'portfolioValue': test_case['portfolioValue'],
        'experience': test_case['experience'],
    }
    
    print_info(f"Ticker: {test_case['ticker']} | Experience: {test_case['experience']} | Portfolio: ₹{test_case['portfolioValue']:,}")
    
    try:
        # Make request
        start_time = time.time()
        response = requests.post(
            f"{BACKEND_URL}/api/analyze",
            json=request_data,
            timeout=10
        )
        response_time = time.time() - start_time
        result['response_time'] = response_time
        
        print_info(f"Response time: {response_time:.2f}s")
        
        if response.status_code != 200:
            print_error(f"HTTP {response.status_code}")
            result['passed'] = False
            return result
        
        data = response.json()
        result['response_data'] = data
        
        # Check for errors
        if 'error' in data:
            print_error(f"API Error: {data['error']}")
            result['passed'] = False
            return result
        
        # Run validation checks
        expected = test_case['expected']
        
        # Check: Has price
        if expected.get('has_price'):
            if 'currentPrice' in data and data['currentPrice'] > 0:
                print_success(f"Price: ₹{data['currentPrice']:,.2f}")
                result['checks'].append(('has_price', True))
            else:
                print_error("Missing or invalid current price")
                result['passed'] = False
                result['checks'].append(('has_price', False))
        
        # Check: Has risk score
        if expected.get('has_risk_score'):
            if 'riskScore' in data and isinstance(data['riskScore'], (int, float)):
                risk_score = data['riskScore']
                risk_level = data.get('riskLevel', 'Unknown')
                
                # Validate risk score is in range
                min_score, max_score = expected.get('risk_score_range', (0, 100))
                if min_score <= risk_score <= max_score:
                    print_success(f"Risk Score: {risk_score}/100 ({risk_level})")
                    result['checks'].append(('has_risk_score', True))
                else:
                    print_error(f"Risk score {risk_score} out of range [{min_score}, {max_score}]")
                    result['passed'] = False
                    result['checks'].append(('has_risk_score', False))
            else:
                print_error("Missing or invalid risk score")
                result['passed'] = False
                result['checks'].append(('has_risk_score', False))
        
        # Check: Has recommendation
        if expected.get('has_recommendation'):
            if 'recommendation' in data:
                rec = data['recommendation']
                rec_class = data.get('recommendationClass', 'unknown')
                confidence = data.get('confidence', 'N/A')
                print_success(f"Recommendation: {rec} ({rec_class}) - Confidence: {confidence}")
                result['checks'].append(('has_recommendation', True))
            else:
                print_error("Missing recommendation")
                result['passed'] = False
                result['checks'].append(('has_recommendation', False))
        
        # Check: Specific recommendation
        if 'recommendation' in expected:
            if data.get('recommendation') == expected['recommendation']:
                print_success(f"Expected recommendation: {expected['recommendation']}")
                result['checks'].append(('correct_recommendation', True))
            else:
                print_warning(f"Expected '{expected['recommendation']}', got '{data.get('recommendation')}'")
        
        # Check: Has targets (for experienced investors)
        if expected.get('has_targets'):
            if data.get('targetPrice1') and data.get('targetPrice2') and data.get('stopLoss'):
                print_success(f"Targets: T1=₹{data['targetPrice1']:,.2f}, T2=₹{data['targetPrice2']:,.2f}, SL=₹{data['stopLoss']:,.2f}")
                result['checks'].append(('has_targets', True))
            else:
                print_error("Missing target prices or stop loss")
                result['passed'] = False
                result['checks'].append(('has_targets', False))
        
        # Check: Has portfolio advice
        if expected.get('has_portfolio_advice'):
            if 'portfolioAdvice' in data and len(data['portfolioAdvice']) > 0:
                print_success(f"Portfolio Advice: {len(data['portfolioAdvice'])} items")
                result['checks'].append(('has_portfolio_advice', True))
            else:
                print_error("Missing portfolio advice")
                result['passed'] = False
                result['checks'].append(('has_portfolio_advice', False))
        
        # Check: Price source
        if expected.get('price_source'):
            price_source = data.get('priceSource', 'Unknown')
            if any(source in price_source for source in expected['price_source']):
                print_success(f"Price Source: {price_source}")
                result['checks'].append(('price_source', True))
            else:
                print_warning(f"Price source: {price_source}")
        
        # Check: Currency conversion for US stocks
        if expected.get('currency_conversion'):
            if data.get('currentPrice', 0) > 1000:  # INR prices are typically larger
                print_success("Currency conversion applied (USD → INR)")
                result['checks'].append(('currency_conversion', True))
            else:
                print_warning("Currency conversion may not be applied")
        
        # Check: Lower risk capacity for elderly
        if expected.get('lower_risk_capacity'):
            risk_capacity = data.get('riskCapacityScore', 50)
            if risk_capacity < 50:
                print_success(f"Risk capacity adjusted for age: {risk_capacity}")
                result['checks'].append(('lower_risk_capacity', True))
            else:
                print_warning(f"Risk capacity not reduced: {risk_capacity}")
        
    except requests.exceptions.Timeout:
        print_error("Request timeout (>10s)")
        result['passed'] = False
    except requests.exceptions.RequestException as e:
        print_error(f"Request failed: {e}")
        result['passed'] = False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        result['passed'] = False
    
    return result

def calculate_accuracy_metrics(results):
    """Calculate accuracy metrics"""
    print_header("ACCURACY METRICS")
    
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r['passed'])
    failed_tests = total_tests - passed_tests
    
    accuracy = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    # Calculate check-level accuracy
    total_checks = sum(len(r['checks']) for r in results)
    passed_checks = sum(sum(1 for check in r['checks'] if check[1]) for r in results)
    check_accuracy = (passed_checks / total_checks * 100) if total_checks > 0 else 0
    
    # Average response time
    avg_response_time = sum(r['response_time'] for r in results) / len(results) if results else 0
    
    # Print metrics
    print(f"\n{Fore.CYAN}Overall Test Results:")
    print(f"  Total Tests:        {total_tests}")
    print(f"  {Fore.GREEN}Passed:             {passed_tests} ({accuracy:.1f}%)")
    print(f"  {Fore.RED}Failed:             {failed_tests}")
    print(f"  {Fore.CYAN}Check Accuracy:     {passed_checks}/{total_checks} ({check_accuracy:.1f}%)")
    print(f"  Avg Response Time:  {avg_response_time:.2f}s")
    
    # Print accuracy breakdown by test type
    print(f"\n{Fore.CYAN}Test Breakdown:")
    indian_tests = [r for r in results if r['ticker'] in ['IOC', 'RELIANCE', 'TCS', 'ONGC']]
    us_tests = [r for r in results if r['ticker'] in ['AAPL', 'MSFT', 'GOOGL']]
    edge_tests = [r for r in results if 'Unknown' in r['name'] or 'Low Portfolio' in r['name'] or 'Elderly' in r['name']]
    
    if indian_tests:
        indian_accuracy = sum(1 for r in indian_tests if r['passed']) / len(indian_tests) * 100
        print(f"  Indian Stocks:      {indian_accuracy:.1f}%")
    
    if us_tests:
        us_accuracy = sum(1 for r in us_tests if r['passed']) / len(us_tests) * 100
        print(f"  US Stocks:          {us_accuracy:.1f}%")
    
    if edge_tests:
        edge_accuracy = sum(1 for r in edge_tests if r['passed']) / len(edge_tests) * 100
        print(f"  Edge Cases:         {edge_accuracy:.1f}%")
    
    return {
        'total_tests': total_tests,
        'passed_tests': passed_tests,
        'failed_tests': failed_tests,
        'accuracy': accuracy,
        'check_accuracy': check_accuracy,
        'avg_response_time': avg_response_time,
    }

def generate_report(results, metrics):
    """Generate detailed HTML report"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QuantumAdvisor Test Report</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0a0c10;
            color: #e8eaf0;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{
            background: linear-gradient(135deg, #7c6ef5, #00e5be);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.5rem;
            margin-bottom: 10px;
        }}
        .timestamp {{ color: #6b7280; margin-bottom: 30px; }}
        .metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        .metric-card {{
            background: #111318;
            border: 1px solid #232735;
            border-radius: 12px;
            padding: 20px;
        }}
        .metric-label {{
            font-size: 0.85rem;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 8px;
        }}
        .metric-value {{
            font-size: 2rem;
            font-weight: 700;
            color: #00e5be;
        }}
        .metric-value.warning {{ color: #f5a623; }}
        .metric-value.danger {{ color: #ff4757; }}
        .test-results {{
            background: #111318;
            border: 1px solid #232735;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }}
        .test-item {{
            border-bottom: 1px solid #232735;
            padding: 15px 0;
        }}
        .test-item:last-child {{ border-bottom: none; }}
        .test-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
        }}
        .test-status {{
            width: 20px;
            height: 20px;
            border-radius: 50%;
            display: inline-block;
        }}
        .test-status.passed {{ background: #00e5be; }}
        .test-status.failed {{ background: #ff4757; }}
        .test-name {{ font-size: 1.1rem; font-weight: 600; }}
        .test-details {{ color: #a0a8bf; font-size: 0.9rem; margin-top: 5px; }}
        .check-list {{
            margin-top: 10px;
            padding-left: 30px;
        }}
        .check-item {{
            font-size: 0.85rem;
            color: #6b7280;
            margin: 3px 0;
        }}
        .check-item.passed {{ color: #00e5be; }}
        .check-item.failed {{ color: #ff4757; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>QuantumAdvisor Test Report</h1>
        <div class="timestamp">Generated: {timestamp}</div>
        
        <div class="metrics">
            <div class="metric-card">
                <div class="metric-label">Overall Accuracy</div>
                <div class="metric-value">{metrics['accuracy']:.1f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Tests Passed</div>
                <div class="metric-value {'warning' if metrics['passed_tests'] < metrics['total_tests'] else ''}">{metrics['passed_tests']}/{metrics['total_tests']}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Check Accuracy</div>
                <div class="metric-value">{metrics['check_accuracy']:.1f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Avg Response Time</div>
                <div class="metric-value">{metrics['avg_response_time']:.2f}s</div>
            </div>
        </div>
        
        <div class="test-results">
            <h2 style="margin-bottom: 20px;">Test Results</h2>
"""
    
    for result in results:
        status_class = 'passed' if result['passed'] else 'failed'
        status_text = '✅ PASSED' if result['passed'] else '❌ FAILED'
        
        html += f"""
            <div class="test-item">
                <div class="test-header">
                    <span class="test-status {status_class}"></span>
                    <span class="test-name">{result['name']}</span>
                </div>
                <div class="test-details">
                    Ticker: {result['ticker']} | Response Time: {result['response_time']:.2f}s | Status: {status_text}
                </div>
"""
        
        if result['checks']:
            html += '<div class="check-list">'
            for check_name, check_passed in result['checks']:
                check_class = 'passed' if check_passed else 'failed'
                check_icon = '✓' if check_passed else '✗'
                html += f'<div class="check-item {check_class}">{check_icon} {check_name}</div>'
            html += '</div>'
        
        html += '</div>'
    
    html += """
        </div>
    </div>
</body>
</html>
"""
    
    # Save report
    report_filename = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    with open(report_filename, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print_success(f"HTML report saved: {report_filename}")
    return report_filename

def main():
    """Main test runner"""
    print_header("QUANTUMADVISOR TEST SUITE")
    print(Fore.CYAN + f"Testing webapp at: {BACKEND_URL}")
    print(Fore.CYAN + f"Total test cases: {len(TEST_CASES)}\n")
    
    # Check backend health
    if not check_backend_health():
        print_error("\n❌ Backend is not running. Please start the backend first.")
        print_info("Run: python MARKETSTACK_backend.py")
        return
    
    print_success("\n✅ Backend is ready! Starting tests...\n")
    time.sleep(1)
    
    # Run all tests
    results = []
    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"\n{Fore.MAGENTA}[{i}/{len(TEST_CASES)}]", end=" ")
        result = run_test_case(test_case)
        results.append(result)
        time.sleep(0.5)  # Small delay between tests
    
    # Calculate metrics
    metrics = calculate_accuracy_metrics(results)
    
    # Generate report
    print_header("GENERATING REPORT")
    report_file = generate_report(results, metrics)
    
    # Final summary
    print_header("TEST SUMMARY")
    if metrics['accuracy'] == 100:
        print(Fore.GREEN + Style.BRIGHT + "🎉 ALL TESTS PASSED! YOUR WEBAPP IS WORKING PERFECTLY!")
    elif metrics['accuracy'] >= 80:
        print(Fore.YELLOW + "⚠️  MOST TESTS PASSED. SOME ISSUES FOUND.")
    else:
        print(Fore.RED + "❌ MULTIPLE FAILURES DETECTED. PLEASE REVIEW.")
    
    print(f"\n{Fore.CYAN}✅ Test suite completed!")
    print(f"{Fore.CYAN}📊 View detailed report: {report_file}")
    print(f"{Fore.CYAN}📈 Overall Accuracy: {metrics['accuracy']:.1f}%\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}Test suite interrupted by user.")
    except Exception as e:
        print(f"\n\n{Fore.RED}Fatal error: {e}")
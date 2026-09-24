# Generates per-patient audit report and comprehensive HTML execution report

import os
from datetime import datetime

def generate_execution_report(report_data, output_dir="downloads", custom_filename=None):
    """
    Generate a comprehensive HTML report showing execution statistics.
    
    Args:
        report_data: Dict with report statistics
                    Example: {
                        'total_patients': 19,
                        'processed_patients': 18,
                        'skipped_patients': 1,
                        'total_files_downloaded': 150,
                        'patients': [
                            {
                                'patient_id': '156640',
                                'patient_name': 'John Doe',
                                'status': 'Completed',
                                'patient_details': 1,
                                'encounters': 5,
                                'consent_forms': 2,
                                'invoices': 3,
                                'images': 10,
                                'membership_invoices': 1,
                                'appointment_history': 1,
                                'available_credits': 1,
                                'service_history': 1,
                                'sms_log': 1,
                                'total_files': 26
                            },
                            ...
                        ]
                    }
        output_dir: Base output directory where report will be saved
        custom_filename: Optional custom filename (e.g., 'Facility_One_Export_Report_04-30-2026.html')
    
    Returns:
        Path to the generated HTML report
    """
    
    # Extract data
    total_patients = report_data.get('total_patients', 0)
    processed_patients = report_data.get('processed_patients', 0)
    skipped_patients = report_data.get('skipped_patients', 0)
    total_files_downloaded = report_data.get('total_files_downloaded', 0)
    patients_list = report_data.get('patients', [])
    
    # Calculate statistics
    completed_patients = sum(1 for p in patients_list if p.get('status') == 'Completed')
    failed_patients = sum(1 for p in patients_list if p.get('status') == 'Failed')
    # Partial patients are those that were processed but not completed or failed
    # In your system, skipped patients should not be counted as partial
    partial_patients = max(0, processed_patients - completed_patients - failed_patients)
    
    # Calculate file counts by type
    total_patient_details = sum(p.get('patient_details', 0) for p in patients_list)
    total_encounters = sum(p.get('encounters', 0) for p in patients_list)
    total_consent_forms = sum(p.get('consent_forms', 0) for p in patients_list)
    total_invoices = sum(p.get('invoices', 0) for p in patients_list)
    total_images = sum(p.get('images', 0) for p in patients_list)
    total_membership_invoices = sum(p.get('membership_invoices', 0) for p in patients_list)
    total_appointment_history = sum(p.get('appointment_history', 0) for p in patients_list)
    total_available_credits = sum(p.get('available_credits', 0) for p in patients_list)
    total_service_history = sum(p.get('service_history', 0) for p in patients_list)
    total_sms_log = sum(p.get('sms_log', 0) for p in patients_list)
    
    # Generate HTML
    facility_name = report_data.get('facility_name', 'CalystaPro EMR')  # Get from data or default
    total_files_success = total_files_downloaded
    total_files_failed = 0
    total_patient_details_files = total_patient_details
    total_patient_details_failed = 0
    total_encounter_files = total_encounters
    total_encounter_failed = 0
    total_consent_files = total_consent_forms
    total_consent_failed = 0
    total_invoice_files = total_invoices
    total_invoice_failed = 0
    total_image_files = total_images
    total_image_failed = 0
    total_membership_invoice_files = total_membership_invoices
    total_membership_invoice_failed = 0
    total_appointment_history_files = total_appointment_history
    total_appointment_history_failed = 0
    total_available_credits_files = total_available_credits
    total_available_credits_failed = 0
    total_service_history_files = total_service_history
    total_service_history_failed = 0
    total_sms_log_files = total_sms_log
    total_sms_log_failed = 0
    
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{facility_name} - Export Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .header p {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        
        .summary-section {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            padding: 40px;
            background: #f8f9fa;
        }}
        
        .summary-card {{
            background: white;
            padding: 25px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            border-left: 5px solid #667eea;
        }}
        
        .summary-card h3 {{
            color: #667eea;
            font-size: 0.9em;
            text-transform: uppercase;
            margin-bottom: 10px;
            letter-spacing: 1px;
        }}
        
        .summary-card .value {{
            font-size: 2.2em;
            font-weight: bold;
            color: #333;
        }}
        
        .summary-card.success {{
            border-left-color: #10b981;
        }}
        
        .summary-card.success h3 {{
            color: #10b981;
        }}
        
        .summary-card.warning {{
            border-left-color: #f59e0b;
        }}
        
        .summary-card.warning h3 {{
            color: #f59e0b;
        }}
        
        .summary-card.danger {{
            border-left-color: #ef4444;
        }}
        
        .summary-card.danger h3 {{
            color: #ef4444;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-top: 15px;
        }}
        
        .stat-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e5e7eb;
        }}
        
        .stat-label {{
            font-weight: 500;
            color: #666;
        }}
        
        .stat-value {{
            font-weight: bold;
            color: #333;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .section-title {{
            font-size: 1.8em;
            color: #333;
            margin: 30px 0 20px 0;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }}
        
        thead {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        
        th {{
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }}
        
        td {{
            padding: 12px 15px;
            border-bottom: 1px solid #e5e7eb;
        }}
        
        tbody tr:hover {{
            background: #f8f9fa;
        }}
        
        tbody tr:nth-child(even) {{
            background: #fafbfc;
        }}
        
        .patient-id {{
            font-weight: bold;
            color: #667eea;
        }}
        
        .status-badge {{
            display: inline-block;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
            text-transform: uppercase;
        }}
        
        .status-completed {{
            background: #d1fae5;
            color: #065f46;
        }}
        
        .status-partial {{
            background: #fed7aa;
            color: #92400e;
        }}
        
        .status-failed {{
            background: #fee2e2;
            color: #991b1b;
        }}
        
        .file-count {{
            display: flex;
            gap: 10px;
            font-size: 0.9em;
        }}
        
        .success-count {{
            color: #10b981;
            font-weight: bold;
        }}
        
        .failed-count {{
            color: #ef4444;
            font-weight: bold;
        }}
        
        .efficiency-bar {{
            width: 100%;
            height: 20px;
            background: #e5e7eb;
            border-radius: 10px;
            overflow: hidden;
            margin: 10px 0;
        }}
        
        .efficiency-fill {{
            height: 100%;
            background: linear-gradient(90deg, #10b981 0%, #06b6d4 100%);
            transition: width 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 0.8em;
            font-weight: bold;
        }}
        
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            border-top: 1px solid #e5e7eb;
            font-size: 0.9em;
        }}
        
        .timestamp {{
            color: #2563eb;
            font-size: 1.1em;
            font-weight: 600;
            background: linear-gradient(135deg, #f8fafc, #e2e8f0);
            padding: 12px 20px;
            border-radius: 8px;
            border: 1px solid #cbd5e1;
            text-align: center;
            margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        .highlight {{
            background: #fef08a;
            padding: 2px 6px;
            border-radius: 3px;
        }}
        
        .charts-container {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 30px;
            margin: 30px 0;
        }}
        
        .chart-card {{
            background: white;
            padding: 25px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }}
        
        .chart-card h3 {{
            color: #333;
            margin-bottom: 20px;
            font-size: 1.3em;
            text-align: center;
        }}
        
        .chart-wrapper {{
            position: relative;
            height: 300px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>📊 {facility_name} - Export Report</h1>
            <p>Total Patients: <strong>{total_patients}</strong> | Processed: <strong>{processed_patients}</strong> | Skipped: <strong>{skipped_patients}</strong></p>
            <p class="timestamp">🕒 Report Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
        </div>
        
        <!-- Summary Cards -->
        <div class="summary-section">
            <!-- Total Patients -->
            <div class="summary-card">
                <h3>👥 Total Patients</h3>
                <div class="value">{total_patients}</div>
            </div>
            
            <!-- Completed Patients -->
            <div class="summary-card success">
                <h3>✓ Completed</h3>
                <div class="value">{completed_patients}</div>
            </div>
            
            <!-- Partial Patients -->
            <div class="summary-card warning">
                <h3>⚠ Partial</h3>
                <div class="value">{partial_patients}</div>
            </div>
            
            <!-- Failed Patients -->
            <div class="summary-card danger">
                <h3>✗ Failed</h3>
                <div class="value">{failed_patients}</div>
            </div>
            
            <!-- Total Files Downloaded -->
            <div class="summary-card success">
                <h3>📄 Files Downloaded</h3>
                <div class="value">{total_files_success}</div>
            </div>
            
            <!-- Total Files Failed -->
            <div class="summary-card danger">
                <h3>📄 Files Failed</h3>
                <div class="value">{total_files_failed}</div>
            </div>
            
            <!-- Overall Efficiency -->
            <div class="summary-card">
                <h3>⚡ Overall Efficiency</h3>
                <div class="value">{(processed_patients/total_patients*100) if total_patients > 0 else 0:.1f}%</div>
                <div class="efficiency-bar">
                    <div class="efficiency-fill" style="width: {(processed_patients/total_patients*100) if total_patients > 0 else 0}%">
                        {(processed_patients/total_patients*100) if total_patients > 0 else 0:.0f}%
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Main Content -->
        <div class="content">
            <!-- Charts Section -->
            <h2 class="section-title">📈 Visual Analytics</h2>
            <div class="charts-container">
                <!-- Patient Status Pie Chart -->
                <div class="chart-card">
                    <h3>Patient Status Distribution</h3>
                    <div class="chart-wrapper">
                        <canvas id="patientStatusChart"></canvas>
                    </div>
                </div>
                
                <!-- Document Type Bar Chart -->
                <div class="chart-card">
                    <h3>Documents by Type (Success vs Failed)</h3>
                    <div class="chart-wrapper">
                        <canvas id="documentTypeChart"></canvas>
                    </div>
                </div>
                
                <!-- File Success Rate Pie Chart -->
                <div class="chart-card">
                    <h3>Overall File Success Rate</h3>
                    <div class="chart-wrapper">
                        <canvas id="successRateChart"></canvas>
                    </div>
                </div>
                
                <!-- Document Distribution Doughnut Chart -->
                <div class="chart-card">
                    <h3>File Distribution by Document Type</h3>
                    <div class="chart-wrapper">
                        <canvas id="documentDistributionChart"></canvas>
                    </div>
                </div>
            </div>
            
            <!-- Document Type Statistics -->
            <h2 class="section-title">📋 Document Type Statistics</h2>
            <div class="summary-section">
                <div class="summary-card">
                    <h3>👤 Patient Details</h3>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <span class="stat-label">Success:</span>
                            <span class="stat-value success-count">{total_patient_details_files}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Failed:</span>
                            <span class="stat-value failed-count">{total_patient_details_failed}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Total:</span>
                            <span class="stat-value">{total_patient_details_files + total_patient_details_failed}</span>
                        </div>
                    </div>
                </div>
                
                <div class="summary-card">
                    <h3>🏥 Encounters</h3>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <span class="stat-label">Success:</span>
                            <span class="stat-value success-count">{total_encounter_files}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Failed:</span>
                            <span class="stat-value failed-count">{total_encounter_failed}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Total:</span>
                            <span class="stat-value">{total_encounter_files + total_encounter_failed}</span>
                        </div>
                    </div>
                </div>
                
                <div class="summary-card">
                    <h3>📝 Consent Forms</h3>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <span class="stat-label">Success:</span>
                            <span class="stat-value success-count">{total_consent_files}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Failed:</span>
                            <span class="stat-value failed-count">{total_consent_failed}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Total:</span>
                            <span class="stat-value">{total_consent_files + total_consent_failed}</span>
                        </div>
                    </div>
                </div>
                
                <div class="summary-card">
                    <h3>💳 Invoices</h3>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <span class="stat-label">Success:</span>
                            <span class="stat-value success-count">{total_invoice_files}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Failed:</span>
                            <span class="stat-value failed-count">{total_invoice_failed}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Total:</span>
                            <span class="stat-value">{total_invoice_files + total_invoice_failed}</span>
                        </div>
                    </div>
                </div>
                
                <div class="summary-card">
                    <h3>📷 Patient Images</h3>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <span class="stat-label">Success:</span>
                            <span class="stat-value success-count">{total_image_files}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Failed:</span>
                            <span class="stat-value failed-count">{total_image_failed}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Total:</span>
                            <span class="stat-value">{total_image_files + total_image_failed}</span>
                        </div>
                    </div>
                </div>
                
                <div class="summary-card">
                    <h3>🏥 Membership Invoices</h3>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <span class="stat-label">Success:</span>
                            <span class="stat-value success-count">{total_membership_invoice_files}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Failed:</span>
                            <span class="stat-value failed-count">{total_membership_invoice_failed}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Total:</span>
                            <span class="stat-value">{total_membership_invoice_files + total_membership_invoice_failed}</span>
                        </div>
                    </div>
                </div>
                
                <div class="summary-card">
                    <h3>📅 Appointment History</h3>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <span class="stat-label">Success:</span>
                            <span class="stat-value success-count">{total_appointment_history_files}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Failed:</span>
                            <span class="stat-value failed-count">{total_appointment_history_failed}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Total:</span>
                            <span class="stat-value">{total_appointment_history_files + total_appointment_history_failed}</span>
                        </div>
                    </div>
                </div>
                
                <div class="summary-card">
                    <h3>💰 Available Credits</h3>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <span class="stat-label">Success:</span>
                            <span class="stat-value success-count">{total_available_credits_files}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Failed:</span>
                            <span class="stat-value failed-count">{total_available_credits_failed}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Total:</span>
                            <span class="stat-value">{total_available_credits_files + total_available_credits_failed}</span>
                        </div>
                    </div>
                </div>
                
                <div class="summary-card">
                    <h3>🧾 Service History</h3>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <span class="stat-label">Success:</span>
                            <span class="stat-value success-count">{total_service_history_files}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Failed:</span>
                            <span class="stat-value failed-count">{total_service_history_failed}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Total:</span>
                            <span class="stat-value">{total_service_history_files + total_service_history_failed}</span>
                        </div>
                    </div>
                </div>
                
                <div class="summary-card">
                    <h3>💬 SMS Log</h3>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <span class="stat-label">Success:</span>
                            <span class="stat-value success-count">{total_sms_log_files}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Failed:</span>
                            <span class="stat-value failed-count">{total_sms_log_failed}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Total:</span>
                            <span class="stat-value">{total_sms_log_files + total_sms_log_failed}</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Patient Details Table -->
            <h2 class="section-title">👤 Detailed Patient Report</h2>
            <table>
                <thead>
                    <tr>
                        <th>Patient ID</th>
                        <th>Patient Name</th>
                        <th>Status</th>
                        <th>Patient Details</th>
                        <th>Encounters</th>
                        <th>Consent Forms</th>
                        <th>Invoices</th>
                        <th>Images</th>
                        <th>Membership Invoices</th>
                        <th>Appointment History</th>
                        <th>Available Credits</th>
                        <th>Service History</th>
                        <th>SMS Log</th>
                        <th>Total Files</th>
                    </tr>
                </thead>
                <tbody>
                    {_generate_patient_rows(patients_list)}
                </tbody>
            </table>
        </div>
        
        <!-- Footer -->
        <div class="footer">
            <p>Calysta Pro EMR Facility Data Export Tool v1.0 with Playwright</p>
            <p class="timestamp">Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
    
    <script>
        // Patient Status Pie Chart
        const patientStatusCtx = document.getElementById('patientStatusChart').getContext('2d');
        new Chart(patientStatusCtx, {{
            type: 'pie',
            data: {{
                labels: ['Completed', 'Partial', 'Failed'],
                datasets: [{{
                    data: [{completed_patients}, {partial_patients}, {failed_patients}],
                    backgroundColor: [
                        '#10b981',
                        '#f59e0b',
                        '#ef4444'
                    ],
                    borderColor: [
                        '#059669',
                        '#d97706',
                        '#dc2626'
                    ],
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        position: 'bottom'
                    }}
                }}
            }}
        }});
        
        // Document Type Bar Chart
        const documentTypeCtx = document.getElementById('documentTypeChart').getContext('2d');
        new Chart(documentTypeCtx, {{
            type: 'bar',
            data: {{
                labels: ['Patient Details', 'Encounters', 'Consent Forms', 'Invoices', 'Images', 'Membership Invoices', 'Appointment History', 'Available Credits', 'Service History', 'SMS Log'],
                datasets: [
                    {{
                        label: 'Success',
                        data: [{total_patient_details_files}, {total_encounter_files}, {total_consent_files}, {total_invoice_files}, {total_image_files}, {total_membership_invoice_files}, {total_appointment_history_files}, {total_available_credits_files}, {total_service_history_files}, {total_sms_log_files}],
                        backgroundColor: '#10b981',
                        borderColor: '#059669',
                        borderWidth: 1
                    }},
                    {{
                        label: 'Failed',
                        data: [{total_patient_details_failed}, {total_encounter_failed}, {total_consent_failed}, {total_invoice_failed}, {total_image_failed}, {total_membership_invoice_failed}, {total_appointment_history_failed}, {total_available_credits_failed}, {total_service_history_failed}, {total_sms_log_failed}],
                        backgroundColor: '#ef4444',
                        borderColor: '#dc2626',
                        borderWidth: 1
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        position: 'bottom'
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            stepSize: 1
                        }}
                    }}
                }}
            }}
        }});
        
        // Success Rate Pie Chart
        const successRateCtx = document.getElementById('successRateChart').getContext('2d');
        new Chart(successRateCtx, {{
            type: 'doughnut',
            data: {{
                labels: ['Successful Downloads', 'Failed Downloads'],
                datasets: [{{
                    data: [{total_files_success}, {total_files_failed}],
                    backgroundColor: [
                        '#06b6d4',
                        '#f87171'
                    ],
                    borderColor: [
                        '#0891b2',
                        '#dc2626'
                    ],
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        position: 'bottom'
                    }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                let label = context.label || '';
                                if (label) {{
                                    label += ': ';
                                }}
                                label += context.parsed;
                                return label;
                            }}
                        }}
                    }}
                }}
            }}
        }});
        
        // Document Distribution Doughnut Chart
        const documentDistributionCtx = document.getElementById('documentDistributionChart').getContext('2d');
        new Chart(documentDistributionCtx, {{
            type: 'doughnut',
            data: {{
                labels: ['Patient Details', 'Encounters', 'Consent Forms', 'Invoices', 'Images', 'Membership Invoices', 'Appointment History', 'Available Credits', 'Service History', 'SMS Log'],
                datasets: [{{
                    data: [{total_patient_details_files + total_patient_details_failed}, {total_encounter_files + total_encounter_failed}, {total_consent_files + total_consent_failed}, {total_invoice_files + total_invoice_failed}, {total_image_files + total_image_failed}, {total_membership_invoice_files + total_membership_invoice_failed}, {total_appointment_history_files + total_appointment_history_failed}, {total_available_credits_files + total_available_credits_failed}, {total_service_history_files + total_service_history_failed}, {total_sms_log_files + total_sms_log_failed}],
                    backgroundColor: [
                        '#94a3b8',
                        '#667eea',
                        '#764ba2',
                        '#f093fb',
                        '#4ade80',
                        '#fb923c',
                        '#38bdf8',
                        '#fbbf24',
                        '#a78bfa',
                        '#f472b6'
                    ],
                    borderColor: [
                        '#64748b',
                        '#5568d3',
                        '#663a8a',
                        '#dd7ee8',
                        '#22c55e',
                        '#ea580c',
                        '#0ea5e9',
                        '#f59e0b',
                        '#8b5cf6',
                        '#ec4899'
                    ],
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        position: 'bottom'
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""
    
    # Create reports directory if it doesn't exist
    reports_dir = os.path.join(output_dir, 'reports') if 'downloads' in output_dir else output_dir
    os.makedirs(reports_dir, exist_ok=True)
    
    # Generate filename
    if custom_filename:
        report_filename = custom_filename
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_filename = f"EMR_Report_{timestamp}.html"
    
    report_path = os.path.join(reports_dir, report_filename)
    
    # Write HTML file
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"\n✓ HTML Report generated: {report_path}")
    return report_path


def _generate_patient_rows(patients_list):
    """Generate table rows for each patient."""
    rows = []
    for patient in patients_list:
        patient_id = patient.get('patient_id', 'N/A')
        patient_name = patient.get('patient_name', 'Unknown')
        status = patient.get('status', 'Unknown')
        
        encounters = patient.get('encounters', 0)
        consent_forms = patient.get('consent_forms', 0)
        invoices = patient.get('invoices', 0)
        images = patient.get('images', 0)
        membership_invoices = patient.get('membership_invoices', 0)
        appointment_history = patient.get('appointment_history', 0)
        available_credits = patient.get('available_credits', 0)
        service_history = patient.get('service_history', 0)
        sms_log = patient.get('sms_log', 0)
        patient_details = patient.get('patient_details', 0)
        total_files = patient.get('total_files', 0)
        
        status_class = f"status-{status.lower()}"
        
        row = f"""
            <tr>
                <td class="patient-id">{patient_id}</td>
                <td>{patient_name}</td>
                <td><span class="status-badge {status_class}">{status}</span></td>
                <td>{patient_details}</td>
                <td>{encounters}</td>
                <td>{consent_forms}</td>
                <td>{invoices}</td>
                <td>{images}</td>
                <td>{membership_invoices}</td>
                <td>{appointment_history}</td>
                <td>{available_credits}</td>
                <td>{service_history}</td>
                <td>{sms_log}</td>
                <td><strong>{total_files}</strong></td>
            </tr>
        """
        rows.append(row)
    
    return '\n'.join(rows)


def generate_audit_report(facility, patient_id, summary, errors):
    """Legacy function placeholder for per-patient audit reports."""
    pass  # Can be extended in future for detailed per-patient reports

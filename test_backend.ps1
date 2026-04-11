# Comprehensive Backend Testing Script
# Tests all API endpoints for the Deployment Automation Tool

Write-Host "`n=== DEPLOYMENT AUTOMATION TOOL - BACKEND TEST SUITE ===" -ForegroundColor Cyan
Write-Host "Testing all endpoints...`n" -ForegroundColor White

$baseUrl = "http://127.0.0.1:8000"
$passedTests = 0
$failedTests = 0

# Helper function to test endpoint
function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Url,
        [string]$Method,
        [string]$Body = $null
    )
    
    Write-Host "Testing: $Name" -ForegroundColor Yellow
    try {
        if ($Body) {
            $response = Invoke-RestMethod -Uri $Url -Method $Method -ContentType "application/json" -Body $Body -ErrorAction Stop
        } else {
            $response = Invoke-RestMethod -Uri $Url -Method $Method -ErrorAction Stop
        }
        Write-Host "PASSED: $Name" -ForegroundColor Green
        Write-Host ($response | ConvertTo-Json -Depth 3)
        Write-Host ""
        return $response
    } catch {
        Write-Host "FAILED: $Name" -ForegroundColor Red
        Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host ""
        return $null
    }
}

# Wait for server to start
Write-Host "Waiting for server to be ready..." -ForegroundColor Cyan
Start-Sleep -Seconds 3

# Test 1: Health Check (Root endpoint)
Write-Host "`n--- TEST 1: Health Check ---" -ForegroundColor Magenta
$result = Test-Endpoint -Name "Root Health Check" -Url "$baseUrl/" -Method "GET"
if ($result) { $passedTests++ } else { $failedTests++ }

# Test 2: GitHub Repository Analysis
Write-Host "`n--- TEST 2: GitHub Repository Analysis ---" -ForegroundColor Magenta
$analyzeBody = @{
    github_url = "https://github.com/vercel/next.js"
} | ConvertTo-Json

$result = Test-Endpoint -Name "Analyze Next.js Repository" -Url "$baseUrl/api/analyze" -Method "POST" -Body $analyzeBody
if ($result) { $passedTests++ } else { $failedTests++ }

# Test 3: Analyze React App
Write-Host "`n--- TEST 3: Analyze React Repository ---" -ForegroundColor Magenta
$reactBody = @{
    github_url = "https://github.com/facebook/react"
} | ConvertTo-Json

$result = Test-Endpoint -Name "Analyze React Repository" -Url "$baseUrl/api/analyze" -Method "POST" -Body $reactBody
if ($result) { $passedTests++ } else { $failedTests++ }

# Test 4: Analyze Python/Django App
Write-Host "`n--- TEST 4: Analyze Django Repository ---" -ForegroundColor Magenta
$djangoBody = @{
    github_url = "https://github.com/django/django"
} | ConvertTo-Json

$result = Test-Endpoint -Name "Analyze Django Repository" -Url "$baseUrl/api/analyze" -Method "POST" -Body $djangoBody
if ($result) { $passedTests++ } else { $failedTests++ }

# Test 5: Create Workflow
Write-Host "`n--- TEST 5: Create Workflow ---" -ForegroundColor Magenta
$workflowBody = @{
    name = "Test Deployment Workflow"
    description = "Testing automated deployment"
} | ConvertTo-Json

$workflow = Test-Endpoint -Name "Create Workflow" -Url "$baseUrl/api/workflows" -Method "POST" -Body $workflowBody
if ($workflow) { $passedTests++ } else { $failedTests++ }

# Test 6: List Workflows
Write-Host "`n--- TEST 6: List Workflow Runs ---" -ForegroundColor Magenta
$result = Test-Endpoint -Name "List All Workflow Runs" -Url "$baseUrl/api/workflows/runs" -Method "GET"
if ($result) { $passedTests++ } else { $failedTests++ }

# Test 7: Get Specific Workflow Run
if ($workflow -and $workflow.id) {
    Write-Host "`n--- TEST 7: Get Workflow Run Details ---" -ForegroundColor Magenta
    $result = Test-Endpoint -Name "Get Workflow Run $($workflow.id)" -Url "$baseUrl/api/workflows/runs/$($workflow.id)" -Method "GET"
    if ($result) { $passedTests++ } else { $failedTests++ }
    
    # Test 8: Get Workflow Steps
    Write-Host "`n--- TEST 8: Get Workflow Steps ---" -ForegroundColor Magenta
    $result = Test-Endpoint -Name "Get Steps for Workflow $($workflow.id)" -Url "$baseUrl/api/workflows/runs/$($workflow.id)/steps" -Method "GET"
    if ($result) { $passedTests++ } else { $failedTests++ }
    
    # Test 9: Approve Workflow
    Write-Host "`n--- TEST 9: Approve Workflow ---" -ForegroundColor Magenta
    $approveBody = @{
        approved = $true
    } | ConvertTo-Json
    $result = Test-Endpoint -Name "Approve Workflow $($workflow.id)" -Url "$baseUrl/api/workflows/runs/$($workflow.id)/approve" -Method "POST" -Body $approveBody
    if ($result) { $passedTests++ } else { $failedTests++ }
    
    # Wait for workflow to complete
    Start-Sleep -Seconds 2
    
    # Test 10: Check Final Status
    Write-Host "`n--- TEST 10: Verify Workflow Completion ---" -ForegroundColor Magenta
    $result = Test-Endpoint -Name "Check Final Status" -Url "$baseUrl/api/workflows/runs/$($workflow.id)" -Method "GET"
    if ($result) { $passedTests++ } else { $failedTests++ }
}

# Test 11: API Documentation
Write-Host "`n--- TEST 11: API Documentation Access ---" -ForegroundColor Magenta
try {
    $docs = Invoke-WebRequest -Uri "$baseUrl/docs" -Method GET -UseBasicParsing
    Write-Host "PASSED: API Documentation is accessible" -ForegroundColor Green
    Write-Host "Documentation available at: $baseUrl/docs" -ForegroundColor Cyan
    $passedTests++
} catch {
    Write-Host "FAILED: API Documentation" -ForegroundColor Red
    $failedTests++
}

# Final Summary
Write-Host "`n" + ("="*60) -ForegroundColor Cyan
Write-Host "TEST SUMMARY" -ForegroundColor Cyan
Write-Host ("="*60) -ForegroundColor Cyan
Write-Host "Total Tests: $($passedTests + $failedTests)" -ForegroundColor White
Write-Host "Passed: $passedTests" -ForegroundColor Green
Write-Host "Failed: $failedTests" -ForegroundColor Red
Write-Host ("="*60) -ForegroundColor Cyan

if ($failedTests -eq 0) {
    Write-Host "`nALL TESTS PASSED! Backend is working perfectly!" -ForegroundColor Green
} else {
    Write-Host "`nSome tests failed. Please review the errors above." -ForegroundColor Yellow
}

Write-Host "`nServer is running at: $baseUrl" -ForegroundColor Cyan
Write-Host "API Docs: $baseUrl/docs" -ForegroundColor Cyan
Write-Host "Interactive API: $baseUrl/redoc" -ForegroundColor Cyan

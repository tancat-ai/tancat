# Define paths
$SourceDir = ".\markdown_docs"
$OutputFile = ".\notebook_upload.md"

# Remove the old build artifact if it exists so we start fresh
if (Test-Path $OutputFile) { Remove-Item $OutputFile -Force }

# Gather ALL markdown files from all subfolders using -Recurse
# Using Resolve-Path makes the file banners show a clean relative path
Get-ChildItem -Path "$SourceDir\*.md" -Recurse | ForEach-Object {
    # This creates a clean relative path (e.g., markdown_docs/cli/main.py.md)
    $RelativePath = $_.FullName.Replace((Get-Location).Path, "").TrimStart("\")
    
    "";
    Get-Content $_.FullName;
    "`n`n`n"
} | Out-File -FilePath $OutputFile -Encoding utf8

Write-Host "Success! Compiled all nested docs into $OutputFile" -ForegroundColor Green
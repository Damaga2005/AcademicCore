; AcademicCore Windows installer (NSIS 3, Modern UI).
; Built from dist\AcademicCore (PyInstaller onedir).
; Installs to Program Files, Start Menu entry, registered uninstall.
; Product identity: AcademicCore 1.0.0 (see version_info.txt / __version__).

!include "MUI2.nsh"
!include "LogicLib.nsh"

Name "AcademicCore"
OutFile "..\..\dist\AcademicCore-1.0.0-Setup.exe"
Unicode True
InstallDir "$PROGRAMFILES64\AcademicCore"
RequestExecutionLevel admin

VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName" "AcademicCore"
VIAddVersionKey "CompanyName" "AcademicCore"
VIAddVersionKey "FileDescription" "AcademicCore academic workspace"
VIAddVersionKey "FileVersion" "1.0.0"
VIAddVersionKey "ProductVersion" "1.0.0"

!define MUI_ICON "academicore.ico"
!define MUI_UNICON "academicore.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\AcademicCore.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch AcademicCore"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "AcademicCore" SecMain
  SetOutPath "$INSTDIR"
  File /r "..\..\dist\AcademicCore\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\AcademicCore"
  CreateShortcut "$SMPROGRAMS\AcademicCore\AcademicCore.lnk" "$INSTDIR\AcademicCore.exe" "" "$INSTDIR\AcademicCore.exe" 0
  CreateShortcut "$SMPROGRAMS\AcademicCore\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcademicCore" "DisplayName" "AcademicCore"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcademicCore" "DisplayVersion" "1.0.0"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcademicCore" "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcademicCore" "DisplayIcon" "$INSTDIR\AcademicCore.exe,0"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcademicCore" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcademicCore" "NoRepair" 1
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\AcademicCore\AcademicCore.lnk"
  Delete "$SMPROGRAMS\AcademicCore\Uninstall.lnk"
  RMDir "$SMPROGRAMS\AcademicCore"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcademicCore"
SectionEnd

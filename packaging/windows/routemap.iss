; Windows installer (Inno Setup 6), built by .github/workflows/installers.yml
; from a build run's "Route Map" folder; nothing is recompiled, so the installed
; app reports the commit that run built.
;
; The names come from routemap/__about__.py through packaging/windows/iss_defines.py:
;   ISCC /DAppName=... /DAppVersion=... /DSourceDir=... routemap.iss
;
; One installer, two modes: per-machine (Program Files, needs admin) or per-user
; (%LOCALAPPDATA%\Programs, no admin). Setup asks; /ALLUSERS or /CURRENTUSER
; choose on the command line. Per machine, the folder is always Program Files:
; no folder page, and a remembered or /DIR= folder is not used, because an
; elevated install and its uninstaller must not live where ordinary users can
; write (RM-14). The PATH task adds {app}\bin, which holds only a launcher for
; the CLI, not the folder with every DLL. Installing over an earlier version uninstalls it
; first (settings live in %APPDATA% and are kept). AppGuid never changes: it is
; how Windows knows a new installer upgrades the old one.

#define AppGuid "260F97E1-3DC2-4D4E-9070-C4D930805B2E"

#ifndef AppName
  #error Pass /DAppName (packaging/windows/iss_defines.py)
#endif
#ifndef SourceDir
  #error Pass /DSourceDir, the build run's "Route Map" folder
#endif

[Setup]
AppId={{{#AppGuid}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#Publisher}
AppPublisherURL={#SiteUrl}
AppSupportURL={#SiteUrl}
AppUpdatesURL={#SiteUrl}/download/
VersionInfoVersion={#NumericVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
UsePreviousAppDir=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\{#GuiExe}
UninstallDisplayName={#AppName}
ChangesEnvironment=yes
CloseApplications=yes
WizardStyle=modern
#ifdef Sign
; scripts/sign-windows.ps1 passes /DSign=1 and /Ssigntool=...: Setup and the
; uninstaller it writes are both signed with the release certificate.
SignTool=signtool
SignedUninstaller=yes
#endif
Compression=lzma2/max
SolidCompression=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "addtopath"; Description: "Add {#CliExe} to PATH (for use in a terminal)"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#GuiExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#GuiExe}"; Tasks: desktopicon

[UninstallDelete]
; The CLI launcher the PATH task writes (see AddLauncher), then the folders.
; After an upgrade the folder was already there when the new version installed,
; so Setup did not record creating it; remove it if (and only if) it is empty.
Type: files; Name: "{app}\bin\*.cmd"
Type: dirifempty; Name: "{app}\bin"
Type: dirifempty; Name: "{app}"

[Run]
Filename: "{app}\{#GuiExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  UserEnv = 'Environment';
  MachineEnv = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';

function EnvRoot: Integer;
begin
  if IsAdminInstallMode then Result := HKEY_LOCAL_MACHINE else Result := HKEY_CURRENT_USER;
end;

function EnvKey: String;
begin
  if IsAdminInstallMode then Result := MachineEnv else Result := UserEnv;
end;

{ PATH holds the install folder at most once, and only while it is installed. }
procedure AddToPath(Dir: String);
var
  Paths: String;
begin
  if not RegQueryStringValue(EnvRoot, EnvKey, 'Path', Paths) then Paths := '';
  if Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';') > 0 then exit;
  if (Paths <> '') and (Copy(Paths, Length(Paths), 1) <> ';') then Paths := Paths + ';';
  RegWriteExpandStringValue(EnvRoot, EnvKey, 'Path', Paths + Dir);
end;

procedure RemoveFromPath(Dir: String);
var
  Paths: String;
  P: Integer;
begin
  if not RegQueryStringValue(EnvRoot, EnvKey, 'Path', Paths) then exit;
  P := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';');
  if P = 0 then exit;
  if P > 1 then Delete(Paths, P - 1, Length(Dir) + 1) else Delete(Paths, 1, Length(Dir) + 1);
  RegWriteExpandStringValue(EnvRoot, EnvKey, 'Path', Paths);
end;

{ Program Files, the only folder a per-machine install uses. }
function MachineDir: String;
begin
  Result := ExpandConstant('{autopf}\{#AppName}');
end;

function UnderProgramFiles(Path: String): Boolean;
begin
  Result := Pos(Uppercase(AddBackslash(ExpandConstant('{autopf}'))), Uppercase(Path)) = 1;
end;

procedure InitializeWizard;
begin
  if IsAdminInstallMode then WizardForm.DirEdit.Text := MachineDir;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = wpSelectDir) and IsAdminInstallMode;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if IsAdminInstallMode and not UnderProgramFiles(ExpandConstant('{app}')) then
    Result := 'A per-machine install goes in ' + MachineDir + ' only.';
end;

var
  { A per-machine install of an earlier version outside Program Files (0.2.0-beta.2
    let the folder be chosen): cleared by RetireOldFolder after this install. }
  OldDir: String;

{ An earlier version in the same mode is uninstalled first, so files that the
  new build no longer has do not stay behind next to it. Per machine its
  uninstaller runs elevated, so only one under Program Files is run; one
  elsewhere is never run (anyone may have replaced it), and its folder is
  cleared by RetireOldFolder instead. }
procedure UninstallPrevious;
var
  Key, Cmd: String;
  Code: Integer;
begin
  Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + '{' + '{#AppGuid}' + '}_is1';
  if not RegQueryStringValue(HKA, Key, 'UninstallString', Cmd) then exit;
  Cmd := RemoveQuotes(Cmd);
  if IsAdminInstallMode and not UnderProgramFiles(Cmd) then begin
    Log('Not running the earlier uninstaller outside Program Files: ' + Cmd);
    if RegQueryStringValue(HKA, Key, 'Inno Setup: App Path', OldDir) then
      OldDir := RemoveBackslashUnlessRoot(OldDir);
    if (OldDir = '') or UnderProgramFiles(AddBackslash(OldDir)) or (Length(OldDir) <= 3) then OldDir := '';
    exit;
  end;
  if FileExists(Cmd) then
    Exec(Cmd, '/VERYSILENT /NORESTART /SUPPRESSMSGBOXES', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

// A junction or symbolic link: never followed when clearing an old folder, so a
// link planted there cannot point the elevated delete anywhere else.
function IsLink(Path: String): Boolean;
var
  Rec: TFindRec;
begin
  Result := True;
  if FindFirst(RemoveBackslashUnlessRoot(Path), Rec) then begin
    Result := (Rec.Attributes and $400) <> 0;   { FILE_ATTRIBUTE_REPARSE_POINT }
    FindClose(Rec);
  end;
end;

// Deletes from OldBase what this install also has (same relative name), the
// old uninstaller and the CLI launcher; anything else stays, and so does any
// folder that is not empty afterwards.
procedure RemoveCopies(OldBase, NewBase, Rel: String);
var
  Rec: TFindRec;
  Name, OldPath: String;
begin
  if not FindFirst(OldBase + Rel + '\*', Rec) then exit;
  try
    repeat
      Name := Rec.Name;
      OldPath := OldBase + Rel + '\' + Name;
      if (Name = '.') or (Name = '..') then continue;
      if (Rec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then begin
        if not IsLink(OldPath) and DirExists(NewBase + Rel + '\' + Name) then begin
          RemoveCopies(OldBase, NewBase, Rel + '\' + Name);
          RemoveDir(OldPath);
        end;
      end else if (Rec.Attributes and $400) = 0 then begin
        if FileExists(NewBase + Rel + '\' + Name)
          or ((Rel = '') and (WildcardMatch(Lowercase(Name), 'unins*.exe') or WildcardMatch(Lowercase(Name), 'unins*.dat')))
          or ((Rel = '\bin') and (Lowercase(Name) = Lowercase(ChangeFileExt('{#CliExe}', '.cmd')))) then
          DeleteFile(OldPath);
      end;
    until not FindNext(Rec);
  finally
    FindClose(Rec);
  end;
end;

// The earlier per-machine folder outside Program Files: off the machine PATH,
// its copies of the app deleted, then the folder itself if nothing else is in it.
procedure RetireOldFolder;
begin
  if (OldDir = '') or (CompareText(OldDir, RemoveBackslashUnlessRoot(ExpandConstant('{app}'))) = 0) then exit;
  RemoveFromPath(OldDir);
  RemoveFromPath(OldDir + '\bin');
  if DirExists(OldDir) and not IsLink(OldDir) then begin
    RemoveCopies(OldDir, ExpandConstant('{app}'), '');
    RemoveDir(OldDir + '\bin');
    if not RemoveDir(OldDir) then Log('Left the earlier folder, which holds files that are not the app''s: ' + OldDir);
  end;
end;

// The app's bin folder holds one file, a launcher for the CLI; that folder goes on PATH.
procedure AddLauncher;
var
  Bin: String;
begin
  Bin := ExpandConstant('{app}\bin');
  ForceDirectories(Bin);
  SaveStringToFile(Bin + '\' + ChangeFileExt('{#CliExe}', '.cmd'),
    '@"%~dp0..\{#CliExe}" %*' + #13#10, False);
  AddToPath(Bin);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then UninstallPrevious;
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('addtopath') then AddLauncher;
  if CurStep = ssPostInstall then RetireOldFolder;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then begin
    RemoveFromPath(ExpandConstant('{app}\bin'));
    { Versions before 0.2.0-beta.3 put the folder itself on PATH. }
    RemoveFromPath(ExpandConstant('{app}'));
  end;
end;

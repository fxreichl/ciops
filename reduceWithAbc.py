
import tempfile
import subprocess
import shutil
import re

from utils import abc_path


def getReadCommand(aig) :
  if aig:
    return "read_aiger "
  else :
    return "read_blif "

def getWriteCommand(aig) :
  if aig:
    return "write_aiger "
  else :
    return "write_blif "

def getNofGates(val, aig = True) :
  if aig :
    x = re.search(r"and\s*=\s*(\d*)", val)
  else :
    x = re.search(r"nd\s*=\s*(\d*)", val)
  if x is None :
    return None
  else :
    return int(x.groups()[0])

def applyABC(fname_in, fname_out, abc_preprocess_cmd, abc_command, aig) :
  spec_suffix = ".aig" if aig else ".blif"
  with tempfile.NamedTemporaryFile(suffix = spec_suffix, delete=True) as tmp1, tempfile.NamedTemporaryFile(suffix = spec_suffix, delete=True) as tmp2:
    write_to = tmp1
    best_tmp = tmp2
    read_command = getReadCommand(aig)
    write_command = getWriteCommand(aig)
    initial_command = f"{read_command + fname_in}; {abc_preprocess_cmd}; {abc_command}; {write_command} {best_tmp.name}; print_stats"
    result = subprocess.run([abc_path, "-c", initial_command], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    abc_applications = 1
    read_command = getReadCommand(aig)
    nof_gates = getNofGates(result.stdout.decode("utf-8"))
    if nof_gates is None :
      return None
    old_nof_gates = nof_gates
    improved = True
    while improved :
      current_cmd = f"{read_command} {best_tmp.name}; {abc_command}; {write_command} {write_to.name}; print_stats"
      result = subprocess.run([abc_path, "-c", current_cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      abc_applications += 1
      nof_gates = getNofGates(result.stdout.decode("utf-8"))
      if nof_gates is None :
        return nof_gates
      if nof_gates < old_nof_gates :
        improved = True
        x = write_to
        write_to = best_tmp
        best_tmp = x
        old_nof_gates = nof_gates
      else :
        improved = False
    if best_tmp is not None :
      shutil.copyfile(best_tmp.name, fname_out)
  print(f"ABC was called: {abc_applications} times")
  return old_nof_gates

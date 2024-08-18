from glob import glob
from rdkit import Chem, RDLogger
from rdkit.Chem.rdchem import BondType
from collections import defaultdict
from tqdm import tqdm
import pickle as pkl 
import numpy as np

RDLogger.DisableLog('rdApp.*')

def loader_fn(fn, remove_frag=True):
    total, success = 0, 0
    with open(fn, 'r') as fr:
        all_lines = []
        for line in fr:
            if not line.strip().startswith("H-"):
                continue
            if remove_frag:
                if "*" in line:
                    continue
            total += 1
            segs = line.strip().split("\t")
            if segs[2].count('(') != segs[2].count(')'):
                continue
            all_lines.append((segs[2], float(segs[1])))

    smiles_scores = defaultdict(list)
    for e in tqdm(all_lines,total=len(all_lines)):
        smi = e[0].replace(' ', '').strip()
        if smi.startswith('[generation]'):
            smi = smi.replace('[generation]', '')
        m = Chem.MolFromSmiles(smi)
        if m is None:
            continue
        s = Chem.MolToSmiles(m)
        c = count_fused_rings(m)
        if c > 3:
            continue
        if has_metal(m):
            continue
        smiles_scores[s].append(e[1])
        success += 1
    return smiles_scores, success, total

def count_fused_rings(mol):
    # The method is generated by GPT-4. 
    ri = mol.GetRingInfo()  
    rings = list(ri.AtomRings())  
    ring_connections = [set() for _ in range(len(rings))]  
  
    for i, ring1 in enumerate(rings):  
        for j in range(i+1, len(rings)):  
            ring2 = rings[j]  
            if len(set(ring1).intersection(set(ring2))) >= 2:  
                ring_connections[i].add(j)  
                ring_connections[j].add(i)  
  
    visited = [False]*len(rings)  
    def dfs(v):  
        visited[v] = True  
        size = 1  
        for w in ring_connections[v]:  
            if not visited[w]:  
                size += dfs(w)  
        return size  
  
    max_fused = 0  
    for i in range(len(rings)):  
        if not visited[i]:  
            max_fused = max(max_fused, dfs(i))  
  
    return max_fused  

def has_metal(mol):  
    metals = set(['Li', 'Be', 'Na', 'Mg', 'Al', 'K', 'Ca', 'Sc', 'Ti', 'V', 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Zn', 'Ga', 'Ge', 'As', 'Se', 'Br', 'Kr', 'Rb', 'Sr', 'Y', 'Zr', 'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd', 'In', 'Sn', 'Sb', 'Te', 'I', 'Xe', 'Cs', 'Ba', 'La', 'Ce', 'Pr', 'Nd', 'Pm', 'Sm', 'Eu', 'Gd', 'Tb', 'Dy', 'Ho', 'Er', 'Tm', 'Yb', 'Lu', 'Hf', 'Ta', 'W', 'Re', 'Os', 'Ir', 'Pt', 'Au', 'Hg', 'Tl', 'Pb', 'Bi', 'Th', 'Pa', 'U', 'Np', 'Pu', 'Am', 'Cm', 'Bk', 'Cf', 'Es', 'Fm', 'Md', 'No', 'Lr', 'Rf', 'Db', 'Sg', 'Bh', 'Hs', 'Mt', 'Ds', 'Rg', 'Cn', 'Nh', 'Fl', 'Mc', 'Lv', 'Ts', 'Og']    )
    for atom in mol.GetAtoms():  
        if atom.GetSymbol() in metals:  
            return True  
    return False  

def fix_CNO(smi):
    mol = Chem.MolFromSmiles(smi)
    rw_mol = Chem.RWMol(mol)

    substruct = Chem.MolFromSmiles('C(=N)O') # do not change it!!!
    matches = rw_mol.GetSubstructMatches(substruct)
    if matches is None or len(matches) == 0:
        return smi

    # Loop over the matches
    for match in matches:
        # Get the indices of the atoms involved in the bond to change
        idx1 = match[0]  # Index of the carbon atom
        idx2 = match[1]  # Index of the nitrogen atom
        idx3 = match[2]
        bond = rw_mol.GetBondBetweenAtoms(idx1, idx2)
        bond.SetBondType(BondType.SINGLE)
        bond = rw_mol.GetBondBetweenAtoms(idx1, idx3)
        bond.SetBondType(BondType.DOUBLE)

    new_mol = rw_mol.GetMol()
    x = Chem.MolToSmiles(new_mol)
    m = Chem.MolFromSmiles(x)
    if m is None:
        return None
    return Chem.MolToSmiles(m)

all_results = {}
success, total = 0, 0

pdb_idx = "4xli"
for prefix in ["nonvae", "vae"]:

    FF = glob(f"{pdb_idx}-results/{prefix}*")

    for fn in FF:
        A, s, t = loader_fn(fn)
        success += s
        total += t
        for k,v in A.items():
            if k in all_results:
                all_results[k].extend(v)
            else:
                all_results[k] = v

    all_results_fix = {}
    for k,v in all_results.items():
        k2 = fix_CNO(k)
        if k2 is None:
            continue
        all_results_fix[k2] = v


    fw = open(f"{pdb_idx}_{prefix}.pkl", "wb")
    pkl.dump(all_results_fix, fw)
    fw.close()

    DB2 = sorted(all_results_fix.items(), key=lambda x: np.mean(x[1]), reverse=True)

    remaining, mol = [], []

    for ele in DB2:
        smi = ele[0]
        if "p" in smi or "P" in smi:
            continue
        m = Chem.MolFromSmiles(smi)
        ssr = Chem.GetSymmSSSR(m)
        if len(ssr) == 0:
            continue
        if len(ssr) >= 6:
            continue
        remaining.append((ele[0], np.mean(ele[1])))
        mol.append(m)

    with open(f"{pdb_idx}_{prefix}_flatten.tsv", 'w') as fw:
        for e in remaining:
            print(f"{e[0]}\t{e[1]}", file=fw)
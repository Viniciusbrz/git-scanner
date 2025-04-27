#!/usr/bin/env python3
"""
GitExtractor - Uma ferramenta para extrair repositórios Git expostos
Autor: Vini XD
"""

import os
import sys
import requests
import re
from urllib.parse import urlparse, urljoin
import concurrent.futures
import argparse

class GitExtractor:
    def __init__(self, url, output_dir, threads=10):
        self.url = url.rstrip('/')
        self.output_dir = output_dir
        self.threads = threads
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'GitExtractor/1.0'})
        
        # Arquivos comuns em um repositório Git
        self.git_files = [
            '.git/HEAD',
            '.git/config',
            '.git/description',
            '.git/info/exclude',
            '.git/objects/info/packs',
            '.git/refs/heads/master',
            '.git/refs/heads/main',
            '.git/index'
        ]
        
        # Padrões para encontrar referências e objetos
        self.ref_pattern = re.compile(r'^[0-9a-f]{40}$')
        self.pack_pattern = re.compile(r'P ([0-9a-f]{40}) (.+\.pack)')
        self.idx_pattern = re.compile(r'[0-9a-f]{40}.idx')
        
        # Criação da estrutura de diretórios
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            
        self.git_dir = os.path.join(self.output_dir, '.git')
        if not os.path.exists(self.git_dir):
            os.makedirs(self.git_dir)
    
    def download_file(self, path):
        """Baixa um arquivo do repositório Git exposto."""
        file_url = urljoin(self.url, path)
        local_path = os.path.join(self.output_dir, path)
        
        try:
            response = self.session.get(file_url, allow_redirects=True)
            
            if response.status_code == 200:
                # Criar diretórios necessários
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                
                # Salvar o arquivo
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                    
                print(f"[+] Baixado: {path}")
                return True
            else:
                print(f"[-] Falha ao baixar {path}: Status {response.status_code}")
                return False
        except Exception as e:
            print(f"[-] Erro ao baixar {path}: {str(e)}")
            return False
    
    def check_git_exists(self):
        """Verifica se o repositório Git está exposto."""
        for git_file in self.git_files[:3]:  # Testa apenas alguns arquivos principais
            url = urljoin(self.url, git_file)
            try:
                response = self.session.head(url)
                if response.status_code == 200:
                    print(f"[+] Repositório Git encontrado! ({git_file} está acessível)")
                    return True
            except Exception:
                pass
                
        print("[-] Nenhum repositório Git exposto encontrado nesta URL.")
        return False
    
    def download_git_files(self):
        """Baixa os arquivos básicos do Git."""
        for git_file in self.git_files:
            self.download_file(git_file)
    
    def extract_hash_from_head(self):
        """Extrai hash do commit da HEAD."""
        head_path = os.path.join(self.git_dir, 'HEAD')
        if not os.path.exists(head_path):
            return None
            
        with open(head_path, 'r') as f:
            content = f.read().strip()
            
        # HEAD pode ser uma referência simbólica
        if content.startswith('ref:'):
            ref_path = content.split('ref: ')[1]
            local_ref_path = os.path.join(self.output_dir, '.git', ref_path)
            
            if os.path.exists(local_ref_path):
                with open(local_ref_path, 'r') as f:
                    return f.read().strip()
                    
            # Tenta baixar a referência do servidor
            self.download_file(os.path.join('.git', ref_path))
            
            if os.path.exists(local_ref_path):
                with open(local_ref_path, 'r') as f:
                    return f.read().strip()
        elif self.ref_pattern.match(content):
            return content
            
        return None
    
    def download_objects(self, hashes):
        """Baixa objetos Git com base em hashes."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = []
            
            for git_hash in hashes:
                if not git_hash or len(git_hash) != 40:
                    continue
                    
                # Formato dos objetos: .git/objects/xx/yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
                obj_dir = git_hash[:2]
                obj_file = git_hash[2:]
                obj_path = f".git/objects/{obj_dir}/{obj_file}"
                
                futures.append(executor.submit(self.download_file, obj_path))
                
            concurrent.futures.wait(futures)
    
    def download_pack_files(self):
        """Baixa arquivos pack e idx."""
        packs_info_path = os.path.join(self.git_dir, 'objects/info/packs')
        if not os.path.exists(packs_info_path):
            return
            
        with open(packs_info_path, 'r') as f:
            content = f.read()
            
        # Procura por arquivos .pack mencionados
        pack_matches = self.pack_pattern.findall(content)
        for _, pack_file in pack_matches:
            pack_path = f".git/objects/pack/{pack_file}"
            idx_path = f".git/objects/pack/{pack_file.replace('.pack', '.idx')}"
            
            self.download_file(pack_path)
            self.download_file(idx_path)
    
    def execute(self):
        """Executa o processo de extração."""
        print(f"[*] Iniciando extração do repositório Git em {self.url}")
        
        if not self.check_git_exists():
            return False
            
        print(f"[*] Baixando arquivos básicos do Git...")
        self.download_git_files()
        
        print(f"[*] Extraindo hash do commit HEAD...")
        head_hash = self.extract_hash_from_head()
        if head_hash:
            print(f"[+] Hash do commit HEAD: {head_hash}")
            self.download_objects([head_hash])
        else:
            print("[-] Não foi possível extrair o hash do commit HEAD")
        
        print(f"[*] Baixando arquivos pack...")
        self.download_pack_files()
        
        print(f"[+] Extração concluída em {self.output_dir}")
        print(f"[+] Para usar o repositório: cd {self.output_dir} && git checkout .")
        
        return True


def main():
    parser = argparse.ArgumentParser(description='GitExtractor - Extrai repositórios Git expostos')
    parser.add_argument('url', help='URL do site com repositório Git exposto')
    parser.add_argument('output_dir', help='Diretório de saída para salvar o repositório')
    parser.add_argument('-t', '--threads', type=int, default=10, help='Número de threads (padrão: 10)')
    
    args = parser.parse_args()
    
    extractor = GitExtractor(args.url, args.output_dir, args.threads)
    extractor.execute()


if __name__ == "__main__":
    main()

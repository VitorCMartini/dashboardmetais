"""
🔐 Gerador de Senhas - Dashboard ICP-MS (Versão Terminal)
===========================================================
Versão otimizada para terminal do Windows/VS Code.

Uso:
    python gerar_senhas_terminal.py

⚠️ IMPORTANTE:
- As senhas serão VISÍVEIS na tela enquanto você digita
- Delete o histórico do terminal após executar
- Use senhas fortes (mínimo 8 caracteres)
"""

import bcrypt
import secrets
import sys


def gerar_hash_bcrypt(senha: str) -> str:
    """Gera hash bcrypt de uma senha."""
    senha_bytes = senha.encode('utf-8')
    salt = bcrypt.gensalt()
    hash_bytes = bcrypt.hashpw(senha_bytes, salt)
    return hash_bytes.decode('utf-8')


def gerar_chave_cookie() -> str:
    """Gera chave aleatória segura para cookies."""
    return secrets.token_urlsafe(32)


def validar_senha(senha: str) -> tuple:
    """Valida força da senha."""
    if len(senha) < 8:
        return False, "Senha muito curta! Use no mínimo 8 caracteres."
    
    if senha.isalpha():
        return False, "Senha muito fraca! Adicione números ou símbolos."
    
    if senha.isnumeric():
        return False, "Senha muito fraca! Adicione letras."
    
    return True, ""


def coletar_senha_terminal(username: str, nome_completo: str) -> str:
    """Coleta senha usando input() normal (senha visível)."""
    while True:
        print(f"\n👤 {nome_completo} (username: {username})")
        print("   Requisitos: mínimo 8 caracteres, misture letras e números")
        
        try:
            senha = input("   Digite a senha: ").strip()
            
            if not senha:
                print("   ❌ Senha vazia! Tente novamente.")
                continue
            
            # Validar força
            valida, erro = validar_senha(senha)
            if not valida:
                print(f"   ❌ {erro}")
                continue
            
            # Confirmar
            senha_confirm = input("   Confirme a senha: ").strip()
            
            if senha != senha_confirm:
                print("   ❌ As senhas não coincidem! Tente novamente.")
                continue
            
            print("   ✅ Senha aceita!")
            return senha
        
        except KeyboardInterrupt:
            print("\n\n⚠️ Operação cancelada pelo usuário.")
            sys.exit(0)
        except EOFError:
            print("\n\n⚠️ Erro de entrada. Tente executar o script diretamente no PowerShell.")
            sys.exit(1)


def main():
    """Função principal."""
    print("\n" + "="*70)
    print("🔐 GERADOR DE SENHAS - Dashboard ICP-MS")
    print("="*70)
    print()
    print("⚠️ AVISO: As senhas serão VISÍVEIS enquanto você digita.")
    print("         Certifique-se de que ninguém está olhando sua tela!")
    print()
    print("📝 Vamos criar senhas para 3 perfis de usuário:")
    print()
    
    # Perfis
    perfis = [
        {
            "username": "admin",
            "nome": "Administrador Sistema",
            "email": "admin@laboratorio.com"
        },
        {
            "username": "analista",
            "nome": "Analista Químico",
            "email": "analista@laboratorio.com"
        },
        {
            "username": "pesquisador",
            "nome": "Pesquisador",
            "email": "pesquisador@laboratorio.com"
        }
    ]
    
    # Coletar senhas e gerar hashes
    print("⏳ Coletando senhas...")
    dados_usuarios = []
    
    for perfil in perfis:
        senha = coletar_senha_terminal(perfil['username'], perfil['nome'])
        
        print("   🔄 Gerando hash bcrypt...")
        hash_senha = gerar_hash_bcrypt(senha)
        
        dados_usuarios.append({
            **perfil,
            'hash': hash_senha
        })
    
    # Gerar chave de cookie
    print("\n" + "-"*70)
    print("🔑 Gerando chave de cookie segura...")
    chave_cookie = gerar_chave_cookie()
    
    # Gerar configuração TOML
    print("\n" + "="*70)
    print("✅ CONFIGURAÇÃO GERADA COM SUCESSO!")
    print("="*70)
    print()
    print("📋 Copie TODO o conteúdo abaixo para .streamlit/secrets.toml:")
    print()
    print("-"*70)
    print()
    
    config = """[credentials]
  [credentials.usernames]
"""
    
    for usuario in dados_usuarios:
        config += f"""    
    # Usuário {usuario['nome']}
    [credentials.usernames.{usuario['username']}]
      email = "{usuario['email']}"
      name = "{usuario['nome']}"
      password = "{usuario['hash']}"
"""
    
    config += """
[cookie]
  expiry_days = 7
  key = "{chave_cookie}"
  name = "auth_cookie_metals"

[preauthorized]
  emails = []
"""
    
    config = config.format(chave_cookie=chave_cookie)
    
    print(config)
    print("-"*70)
    print()
    
    # Salvar em arquivo
    try:
        arquivo_saida = "secrets_gerados.toml"
        with open(arquivo_saida, "w", encoding="utf-8") as f:
            f.write(config)
        
        print(f"✅ Configuração salva em: {arquivo_saida}")
        print()
        print("💾 PRÓXIMOS PASSOS:")
        print(f"   1. Abra o arquivo: {arquivo_saida}")
        print("   2. Copie TODO o conteúdo")
        print("   3. Cole em: .streamlit/secrets.toml (SUBSTITUA todo o conteúdo)")
        print("   4. Salve o arquivo .streamlit/secrets.toml")
        print(f"   5. DELETE o arquivo: {arquivo_saida} (ele contém dados sensíveis!)")
        print("   6. LIMPE o histórico deste terminal (senhas foram exibidas!)")
        print("   7. Execute: streamlit run app.py")
        print()
        print("🧹 Para limpar histórico do PowerShell:")
        print("   Clear-History; Clear-Host")
        print()
    
    except Exception as e:
        print(f"⚠️ Não foi possível salvar: {str(e)}")
        print("   (Você ainda pode copiar manualmente o conteúdo acima)")
        print()
    
    print("="*70)
    print()
    print("⚠️ LEMBRETE DE SEGURANÇA:")
    print("   • Guarde suas senhas em um gerenciador seguro")
    print("   • LIMPE o histórico do terminal (senhas foram exibidas)")
    print("   • NUNCA versione o arquivo secrets.toml no Git")
    print("   • NUNCA compartilhe este arquivo por email/chat")
    print()
    print("🎉 Processo concluído!")
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Erro inesperado: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

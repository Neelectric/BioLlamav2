import sqlite3
import os
from tqdm import tqdm
from functools import lru_cache
import glob
from transformers import AutoTokenizer
import wandb
from wandb import AlertLevel

@lru_cache(maxsize=None)
def get_connection():
    # Establish a connection to the SQLite database
    conn = sqlite3.connect('/root/nfs/pubmed_cleaned_index/lookup_table.db')
    return conn

def init_db():
    # Create a table
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY,
            chunk TEXT NOT NULL
        )
    """)
    conn.commit()

def insert_chunk(chunk):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO chunks (chunk) VALUES (?)", (chunk,))
    conn.commit()

def get_chunk(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT chunk FROM chunks WHERE id = ?", (id,))
    result = cur.fetchone()
    return result[0] if result else None

def split_into_chunks(text, total_token_count, max_chunk_length=32):
    tokens = llama2_tokenizer.encode(text)
    chunks = []
    if len(tokens) < max_chunk_length:
         return [], total_token_count
    for i in range(0, len(tokens), max_chunk_length):
         if (i+max_chunk_length) <= len(tokens):
            chunk = tokens[i:i+max_chunk_length]
            total_token_count += len(chunk)
            decoded = llama2_tokenizer.decode(chunk, skip_special_tokens=True) # crucial to not add "<s>"
            chunks.append(decoded)
    return chunks, total_token_count
def get_db_size(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM chunks")
    result = cur.fetchone()
    return result[0] if result else 0
    
llama_path = "meta-llama/Llama-2-7b-chat-hf"
llama2_tokenizer = AutoTokenizer.from_pretrained(llama_path, cache_dir = "../hf_cache/")
total_token_count = 0


wandb.init(project="biollama_v2", # the project I am working on
           tags=["hf_sft", "BioLlamaV2"]) # the Hyperparameters I want to keep track of

wandb.alert(
    title="Initialising db",
    text=f"starting to build the database",
    level=AlertLevel.WARN,
    wait_duration=300,
)

init_db()  # Initialize the database
source_files = glob.glob("/root/nfs/pubmed_cleaned/*.tsv")
conn = get_connection()  # Establish a connection outside the loop

print("entering  main loop...")
for i, source_file in tqdm(enumerate(source_files)):
    batch_size = 128
    all_chunks = []
    tsv_basename = os.path.basename(source_file).split(".")[0]

    with open(source_file, 'r') as file:
        lines = file.readlines()

        for start_idx in tqdm(range(0, len(lines), batch_size), disable=False):
            all_chunks = []
            end_idx = min(start_idx + batch_size, len(lines))
            batch_abstracts = [line.strip() for line in lines[start_idx:end_idx]]

            for abstract in batch_abstracts:
                chunks, total_token_count = split_into_chunks(abstract, total_token_count)
                if chunks != []:
                    all_chunks += chunks

            for chunk in tqdm(all_chunks, disable=True):
                insert_chunk(chunk)

    print(f"Database size after processing file {source_file}: {get_db_size(conn)}")
    conn.commit()  # Commit changes after each file

conn.close()  # Close the connection when done
print("well done! all iterations complete")
wandb.alert(
    title="Finished building db",
    text=f"sqlite3 done!",
    level=AlertLevel.WARN,
    wait_duration=300,
)
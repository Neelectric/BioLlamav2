### A refactored and cleaned version of db_retrieval.py in BioLlamaV1
### Written by Neel Rajani

from typing import Tuple, List, Optional
from transformers import AutoTokenizer, AutoModel, AutoModelForSequenceClassification, PreTrainedTokenizerFast, PreTrainedTokenizer, BertModel
import faiss
from time import time
import json
import torch
import sqlite3

def load_db(db_name: str, retriever_name: str, neighbour_length: int) -> Tuple[faiss.IndexFlatIP, dict]:
    """
    Args:
        db_name (str): The name of the database to load.
        retriever_name (str): The name of the retriever to use.

    Returns:
        Tuple[faiss.IndexFlatIP, dict]: A tuple containing the loaded FAISS index and JSON object.
    """

    index_path = '/root/nfs/pubmed_cleaned_index/'
    time_before_index_load = time()
    # db_faiss = faiss.read_index(index_path + retriever_name + "_index.faiss")
    # res = faiss.StandardGpuResources()
    cpu_index = faiss.read_index(index_path + retriever_name + "_index.faiss")
    # gpu_index = faiss.GpuIndexFlat(res, cpu_index.d, cpu_index.metric_type)
    # gpu_index = faiss.index_cpu_to_gpu(res, gpu_index, cpu_index)
    time_after_index_load = time()
    time_to_load_index = time_after_index_load - time_before_index_load
    print(f"Time to load index: {time_to_load_index}")
    if retriever_name == "medcpt":
        retriever_name = "definitive"
    time_before_json_load = time()
    with open("/root/nfs/pubmed_cleaned_index/lookup_table_" + retriever_name + ".json", "r") as file:
        db_json = json.load(file)
    time_after_json_load = time()
    time_to_load_json = time_after_json_load - time_before_json_load
    print(f"Time to load json: {time_to_load_json}")
    # db_json = None
    return cpu_index, db_json

def id_2_chunk(id):
    conn = sqlite3.connect('/root/nfs/pubmed_cleaned_index/lookup_table.db')
    cur = conn.cursor()
    cur.execute("SELECT chunk FROM chunks WHERE id = ?", (id,))
    result = cur.fetchone()
    if result:
        print(result[0])  # Print the chunk
        result = result[0]
    else:
        print("Chunk not found")
    conn.close()
    return result


def retrieve(queries: List[str],
             neighbour_length: int,
             query_tokenizer: PreTrainedTokenizerFast | PreTrainedTokenizer,
             query_model: BertModel,
             rerank_tokenizer,
             rerank_model,
             top_k: int,
             k: int,
             db_faiss: faiss.IndexFlatIP, 
             db_json: dict
             ) -> List[str]:
    output = []

    # Per query, we embed using MedCPT, perform FAISS ANN and then rerank if requested
    for query in queries:
        with torch.no_grad(): # This code is taken directly from the MedCPT GitHub/HF tutorial
            encoded = query_tokenizer(query, truncation=True, padding=True, return_tensors="pt",max_length=512,).to("cuda:0")
            embeds = query_model(**encoded).last_hidden_state[:, 0, :]
        
        distances, indices = db_faiss.search(embeds.to('cpu').numpy(), k)
        distances = distances.flatten()
        indices = indices.flatten()
        print(distances)
        print(indices)
        neighbours = [db_json[str(idx)] for idx in indices]
        print(neighbours)
        # neighbours = [id_2_chunk(idx) for idx in indices]
        # continuations = [db_json[str(idx+1)] for idx in indices] #  Could use this to implement continuations
        if k > 1:
            pairs = [[query, neighbour] for neighbour in neighbours]
            with torch.no_grad():
                encoded = rerank_tokenizer(pairs, truncation=True, padding=True, return_tensors="pt", max_length=512,).to("cuda:0")
                logits = rerank_model(**encoded).logits.squeeze(dim=1)
                sorted_scores = sorted(zip(neighbours, logits), key=lambda x: x[1], reverse=True)
                sorted_chunkid_indices = sorted(zip(indices, logits), key=lambda x: x[1], reverse=True) # Could use this to implement continuations
                new_chunks = [x[0] for x in sorted_scores]
                top_chunks = new_chunks[0:top_k]
        else:
            top_chunks = neighbours[0:top_k]
        output.append(top_chunks)
    return output

def main():
    # '. Recent innovative treatment approaches target the multiple pathophysiological defects present in type 2 diabetes. Optimal management should include early'
    queries = [". Recent innovative treatment approaches target the multiple pathophysiological defects present in "]
    db_name = "pma"
    neighbour_length = 32
    verbose = True
    query_tokenizer = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder")
    query_model = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder", device_map = "cuda:0")
    rerank_tokenizer = AutoTokenizer.from_pretrained("ncbi/MedCPT-Cross-Encoder")
    rerank_model = AutoModelForSequenceClassification.from_pretrained("ncbi/MedCPT-Cross-Encoder", device_map = "cuda:0")
    top_k = 5
    k = 20
    db_faiss, db_json = load_db(db_name, "medcpt", neighbour_length)
    print("db loaded, starting to retrieve")
    output = retrieve(queries,  
                      neighbour_length,  
                      query_tokenizer, 
                      query_model, 
                      rerank_tokenizer, 
                      rerank_model, 
                      top_k, 
                      k, 
                      db_faiss, 
                      db_json)
    print(output)

if __name__ == "__main__":
    main()
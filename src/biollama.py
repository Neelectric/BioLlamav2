### A refactored and cleaned version of biollama.py in BioLlamaV1
### Written by Neel Rajani

from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
from time import time
from typing import List
from src.retrieval import load_db


def attach_retriever(biollama, retriever):
    return

# Custom forward pass that stores current input ids as model attribute for later access
def new_forward(biollama, *args, **kwargs):
    if "input_ids" in kwargs:
        biollama.input_ids_biollama = kwargs["input_ids"]
        output = biollama.old_forward(*args, **kwargs)
    else:
        raise Exception("input_ids or labels not found in kwargs")
    return output

def load_RETRO_weights(biollama, model_path, RETRO_layer_ids):
    return

# Adds RMSNorm and LlamaSdpaAttention modules to given layer
def RETRO_fit_layer(layer, i, biollama, torch_dtype):
    return

# Switches specified decoder layers to be a RETRO layer
def RETRO_fit(biollama, RETRO_layer_ids, torch_dtype):
    for i, layer in enumerate(biollama.model.model.layers):
        if i in RETRO_layer_ids:
            RETRO_fit_layer(layer, i, biollama, torch_dtype) 
    return

class BioLlama():
    """
    The fundamental BioLlama class that holds the modified Llama-2 transformers object and all necessary retrieval components
    """
    def __init__(
            self, 
            model_path: str,
            torch_dtype: torch.dtype,
            RETRO_layer_ids: List[int],
            training: bool,
            retriever_name: str,
            db_name: str,
            neighbour_length: int,
            ):
        
        # Model setup
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, cache_dir = "../hf_cache/")
        self.model = AutoModelForCausalLM.from_pretrained(model_path, 
                                                          cache_dir = "../hf_cache/", 
                                                        #   device_map = "auto", 
                                                          device_map = "cuda:0",
                                                          torch_dtype = torch_dtype)
        self.model.generation_config.temperature = None
        self.model.generation_config.use_cache = False # Editing the generation config to use
        self.model.generation_config.do_sample = False # GenerationMode.GREEDY_SEARCH in the hopes
        self.model.generation_config.top_k = None # that this makes generation deterministic
        self.model.generation_config.top_p = None

        # Add RETRO modules and load respective weights if not training
        RETRO_fit(self, RETRO_layer_ids = RETRO_layer_ids, torch_dtype = torch_dtype)
        if not training: load_RETRO_weights(self, model_path = model_path, RETRO_layer_ids = RETRO_layer_ids)

        # save original .forward() call and then replace .forward() with new customized implementation
        self.model.old_forward = self.model.forward
        self.model.forward = new_forward.__get__(self.model)

        # Prepare all retrieval components, ie. retriever, retrieval corpus and retrieved chunk storage
        attach_retriever(self, retriever = retriever_name)
        self.db_faiss, self.db_json = load_db(db_name = db_name, 
                                              retriever_name = retriever_name, 
                                              neighbour_length = neighbour_length)
        self.neighbour_storage = None
        return
    # encode the queries (use the [CLS] last hidden states as the representations)
    
    def generate(self, prompt, max_new_tokens = 50):
        padding = False # keeping this for now, may need to change for batch generation
        inputs = self.tokenizer(prompt, return_tensors="pt", padding=padding)
        self.model.input_ids_biollama = inputs["input_ids"] # Storing the input_ids to access them again later
        self.model.prompt_biollama = prompt # Same for pure prompt
        self.model.generation_config.max_new_tokens = max_new_tokens
        time_before = time()
        generated_tokens = self.model.generate(inputs.input_ids.to(self.device), 
                                               **self.model.generation_config.to_dict())
        time_after = time()
        time_taken = time_after - time_before
        num_new_tokens = len(generated_tokens[0]) - len(inputs.input_ids[0])
        output = self.tokenizer.batch_decode(generated_tokens, skip_special_tokens=True, clean_up_tokenization_spaces=False,)[0]
        return (output, num_new_tokens, time_taken)
    
    


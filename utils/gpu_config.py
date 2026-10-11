"""
GPU Configuration and Force Usage Module
Provides configuration options to control GPU usage in the wargame simulation.
"""

import os
from typing import Dict, Any

# GPU configuration settings
GPU_CONFIG = {
    'force_gpu': os.environ.get('WARGAME_FORCE_GPU', 'false').lower() == 'true',
    'gpu_threshold': int(os.environ.get('WARGAME_GPU_THRESHOLD', '2000')),
    'gpu_stress_test': os.environ.get('WARGAME_GPU_STRESS', 'false').lower() == 'true',
    'gpu_batch_size': int(os.environ.get('WARGAME_GPU_BATCH_SIZE', '1000')),
}

def should_use_gpu(dataset_size: int) -> bool:
    """
    Determine if GPU should be used based on configuration and dataset size.
    
    Args:
        dataset_size: Size of the dataset (e.g., number of hex cells)
        
    Returns:
        True if GPU should be used, False otherwise
    """
    if GPU_CONFIG['force_gpu']:
        print(f"🔥 FORCE GPU MODE: Using GPU regardless of dataset size ({dataset_size})")
        return True
    
    if dataset_size >= GPU_CONFIG['gpu_threshold']:
        print(f"🚀 Dataset large enough for GPU: {dataset_size} >= {GPU_CONFIG['gpu_threshold']}")
        return True
    
    print(f"📊 Dataset too small for GPU efficiency: {dataset_size} < {GPU_CONFIG['gpu_threshold']}")
    return False

def get_gpu_config() -> Dict[str, Any]:
    """Get current GPU configuration."""
    return GPU_CONFIG.copy()

def set_force_gpu(enabled: bool) -> None:
    """Enable or disable force GPU mode."""
    GPU_CONFIG['force_gpu'] = enabled
    print(f"🔧 Force GPU mode: {'ENABLED' if enabled else 'DISABLED'}")

def run_gpu_stress_test():
    """Run GPU stress test to verify GPU functionality."""
    try:
        import cupy as cp
        print("🔥 RUNNING GPU STRESS TEST...")
        
        # Create large computation
        test_size = 3000
        test_data = cp.random.rand(test_size, test_size, dtype=cp.float32)
        
        for i in range(20):
            result = cp.sin(test_data) * cp.cos(test_data)
            result = cp.sqrt(cp.abs(result))
            final = cp.mean(result)
            cp.cuda.Stream.null.synchronize()
            print(f"🔥 GPU stress test iteration {i+1}/20 - CHECK NVTOP!")
        
        del test_data, result
        cp.cuda.Stream.null.synchronize()
        print("✅ GPU stress test complete - GPU should show usage in nvtop")
        
    except Exception as e:
        print(f"❌ GPU stress test failed: {e}")

def print_gpu_status():
    """Print current GPU configuration and status."""
    print("="*50)
    print("🚀 GPU CONFIGURATION STATUS")
    print("="*50)
    print(f"Force GPU: {GPU_CONFIG['force_gpu']}")
    print(f"GPU Threshold: {GPU_CONFIG['gpu_threshold']} cells")
    print(f"GPU Batch Size: {GPU_CONFIG['gpu_batch_size']}")
    print(f"GPU Stress Test: {GPU_CONFIG['gpu_stress_test']}")
    
    try:
        import cupy as cp
        device = cp.cuda.Device()
        mem_info = device.mem_info
        print(f"GPU Available: ✅ YES")
        print(f"GPU Device: {device}")
        print(f"GPU Memory: {mem_info[0]/1e9:.1f}GB free / {mem_info[1]/1e9:.1f}GB total")
    except Exception as e:
        print(f"GPU Available: ❌ NO ({e})")
    
    print("="*50)
    print("To force GPU usage: export WARGAME_FORCE_GPU=true")
    print("To run stress test: export WARGAME_GPU_STRESS=true")
    print("="*50)

if __name__ == "__main__":
    print_gpu_status()
    if GPU_CONFIG['gpu_stress_test']:
        run_gpu_stress_test()
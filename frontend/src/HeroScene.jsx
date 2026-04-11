import React, { useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { 
  OrbitControls, 
  Sphere, 
  MeshDistortMaterial, 
  Float, 
  Environment,
  Points,
  PointMaterial,
} from '@react-three/drei';

// Simple random generator
const randomRange = (min, max) => Math.random() * (max - min) + min;

// Generate particles array
const particleCount = 2000;
const positions = new Float32Array(particleCount * 3);
for (let i = 0; i < particleCount * 3; i++) {
  positions[i] = randomRange(-15, 15);
}

function Starfield() {
  const ref = useRef();
  useFrame((state, delta) => {
    ref.current.rotation.x -= delta / 10;
    ref.current.rotation.y -= delta / 15;
  });

  return (
    <group rotation={[0, 0, Math.PI / 4]}>
      <Points ref={ref} positions={positions} stride={3} frustumCulled={false}>
        <PointMaterial transparent color="#8b5cf6" size={0.05} sizeAttenuation={true} depthWrite={false} />
      </Points>
    </group>
  );
}

function FloatingNodes() {
  const nodes = Array.from({ length: 8 }, () => ({
    position: [randomRange(-5, 5), randomRange(-3, 3), randomRange(-3, 2)],
    scale: randomRange(0.2, 0.6)
  }));

  return (
    <>
      {nodes.map((node, i) => (
        <Float key={i} speed={2} rotationIntensity={1.5} floatIntensity={2}>
          <mesh position={node.position} scale={node.scale}>
            <octahedronGeometry args={[1, 0]} />
            <meshStandardMaterial 
              color={i % 2 === 0 ? "#6366f1" : "#ec4899"} 
              wireframe 
              emissive={i % 2 === 0 ? "#6366f1" : "#ec4899"}
              emissiveIntensity={2} 
            />
          </mesh>
        </Float>
      ))}
    </>
  );
}

function MainOrb() {
  return (
    <Float speed={2} rotationIntensity={1} floatIntensity={1}>
      <Sphere args={[1, 64, 64]} scale={1.8} position={[4, 0, -2]}>
        <MeshDistortMaterial
          color="#120e2b"
          attach="material"
          distort={0.4}
          speed={2}
          roughness={0.2}
          metalness={0.8}
        />
      </Sphere>
      {/* Dynamic light inside the orb */}
      <pointLight position={[4, 0, -2]} color="#6366f1" intensity={50} distance={10} decay={2} />
    </Float>
  );
}

export default function HeroScene() {
  return (
    <div className="canvas-container">
      <Canvas camera={{ position: [0, 0, 8], fov: 60 }} dpr={[1, 2]}>
        <color attach="background" args={['#050505']} />
        
        {/* Illumination */}
        <ambientLight intensity={0.2} />
        <directionalLight position={[10, 10, 5]} intensity={2} color="#ec4899" />
        <directionalLight position={[-10, -10, -5]} intensity={2} color="#6366f1" />
        
        {/* Scene Objects */}
        <MainOrb />
        <FloatingNodes />
        <Starfield />

        {/* Effects & Environment */}
        <Environment preset="city" />
        
        {/* Controls - allow interaction but disable zoom to maintain layout */}
        <OrbitControls 
          enableZoom={false} 
          enablePan={false}
          autoRotate 
          autoRotateSpeed={0.5} 
          maxPolarAngle={Math.PI / 2 + 0.2}
          minPolarAngle={Math.PI / 2 - 0.2}
        />
      </Canvas>
    </div>
  );
}

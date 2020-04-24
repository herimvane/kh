package com.herim.kh.dao;

import org.springframework.data.jpa.repository.JpaRepository;

import com.herim.kh.domain.Role;

public interface RoleRepository extends JpaRepository<Role, String> {
	
	
}

package com.herim.kh.dao;

import org.springframework.data.jpa.repository.JpaRepository;

import com.herim.kh.domain.Permission;

public interface PermissionRepository extends JpaRepository<Permission, String> {
	
	
}

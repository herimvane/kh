package com.herim.kh.dao;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import com.herim.kh.domain.MyConfig;

public interface MyConfigRepository extends JpaRepository<MyConfig, String> {
	
	List<MyConfig> findByKey(String key);
	
	@Query(value = "update myconfig set value = ?2 where key= ?1 ", nativeQuery = true)  
	@Modifying  
	public void updateValue(String key,String value);
	
}
